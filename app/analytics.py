import logging
import threading
import time
from collections import defaultdict
from collections.abc import Iterable
from typing import Any, cast
from urllib.parse import urlsplit

from redis import Redis
from redis.exceptions import RedisError, ResponseError
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session, sessionmaker

from app.models import Click, LinkDailyStat, LinkReferrerDailyStat
from app.timeutils import day_string

logger = logging.getLogger(__name__)

VISITOR_TTL_SECONDS = 60 * 60 * 24 * 400


def visitor_key(link_id: int, day: str) -> str:
    return f"uv:{link_id}:{day}"


def publish_click(
    redis_client: Redis,
    stream: str,
    link_id: int,
    ts: int,
    ip_hash: bytes | None,
    user_agent: str | None,
    referrer: str | None,
) -> None:
    try:
        redis_client.xadd(
            stream,
            {
                "link_id": str(link_id),
                "ts": str(ts),
                "ip_hash": ip_hash.hex() if ip_hash else "",
                "user_agent": (user_agent or "")[:512],
                "referrer": (referrer or "")[:512],
            },
            maxlen=100_000,
            approximate=True,
        )
    except RedisError:
        logger.warning("failed to publish click event", exc_info=True)


class AnalyticsWorker:
    def __init__(
        self,
        redis_client: Redis,
        session_factory: sessionmaker[Session],
        stream: str,
        group: str,
        consumer: str,
    ) -> None:
        self._redis = redis_client
        self._session_factory = session_factory
        self._stream = stream
        self._group = group
        self._consumer = consumer
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, name="analytics-worker", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=5)
        self._redis.close()

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                self._ensure_group()
                break
            except RedisError:
                logger.warning("analytics group setup failed; retrying", exc_info=True)
                time.sleep(1)

        while not self._stop.is_set():
            try:
                response = cast(
                    list[tuple[str, list[tuple[str, dict[str, str]]]]],
                    self._redis.xreadgroup(
                        groupname=self._group,
                        consumername=self._consumer,
                        streams={self._stream: ">"},
                        count=100,
                        block=1000,
                    ),
                )
            except RedisError:
                logger.warning("analytics stream read failed", exc_info=True)
                time.sleep(1)
                continue

            if not response:
                continue

            for _stream, entries in response:
                try:
                    self.process_entries(entries)
                except Exception:
                    logger.exception("analytics batch failed")
                    time.sleep(1)
                else:
                    self._ack(entries)

    def _ensure_group(self) -> None:
        try:
            self._redis.xgroup_create(self._stream, self._group, id="0", mkstream=True)
        except ResponseError as exc:
            if "BUSYGROUP" not in str(exc):
                logger.warning("failed to create consumer group", exc_info=True)

    def _ack(self, entries: Iterable[tuple[str, dict[str, str]]]) -> None:
        entry_ids = [entry_id for entry_id, _ in entries]
        if not entry_ids:
            return
        try:
            self._redis.xack(self._stream, self._group, *entry_ids)
        except RedisError:
            logger.warning("failed to ack analytics events", exc_info=True)

    def process_entries(self, entries: Iterable[tuple[str, dict[str, str]]]) -> int:
        events = [parsed for _, fields in entries if (parsed := self._parse(fields)) is not None]
        if not events:
            return 0

        session = self._session_factory()
        try:
            daily: dict[tuple[int, str], int] = defaultdict(int)
            referrers: dict[tuple[int, str, str], int] = defaultdict(int)
            visitors: dict[tuple[int, str], set[str]] = defaultdict(set)

            for event in events:
                session.add(
                    Click(
                        link_id=event["link_id"],
                        clicked_at=event["ts"],
                        ip_hash=event["ip_hash"],
                        user_agent=event["user_agent"],
                        referrer=event["referrer"],
                    )
                )
                day = day_string(event["ts"])
                daily[(event["link_id"], day)] += 1
                referrers[(event["link_id"], day, event["referrer"])] += 1
                if event["ip_hash"]:
                    visitors[(event["link_id"], day)].add(event["ip_hash"].hex())

            for (link_id, day), count in daily.items():
                statement = sqlite_insert(LinkDailyStat).values(
                    link_id=link_id, day=day, clicks=count
                )
                statement = statement.on_conflict_do_update(
                    index_elements=["link_id", "day"],
                    set_={"clicks": LinkDailyStat.clicks + statement.excluded.clicks},
                )
                session.execute(statement)

            for (link_id, day, referrer), count in referrers.items():
                statement = sqlite_insert(LinkReferrerDailyStat).values(
                    link_id=link_id, day=day, referrer=referrer, clicks=count
                )
                statement = statement.on_conflict_do_update(
                    index_elements=["link_id", "day", "referrer"],
                    set_={"clicks": LinkReferrerDailyStat.clicks + statement.excluded.clicks},
                )
                session.execute(statement)

            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

        for (link_id, day), hashes in visitors.items():
            try:
                self._redis.pfadd(visitor_key(link_id, day), *hashes)
                self._redis.expire(visitor_key(link_id, day), VISITOR_TTL_SECONDS)
            except RedisError:
                logger.warning("failed to update visitor sketch", exc_info=True)

        return len(events)

    def _parse(self, fields: dict[str, str]) -> dict[str, Any] | None:
        try:
            link_id = int(fields.get("link_id", ""))
            ts = int(fields.get("ts", ""))
        except (TypeError, ValueError):
            return None

        ip_hex = fields.get("ip_hash", "")
        try:
            ip_hash = bytes.fromhex(ip_hex) if ip_hex else None
        except ValueError:
            ip_hash = None

        return {
            "link_id": link_id,
            "ts": ts,
            "ip_hash": ip_hash,
            "user_agent": (fields.get("user_agent") or "")[:512] or None,
            "referrer": _normalize_referrer(fields.get("referrer") or ""),
        }


def _normalize_referrer(value: str) -> str:
    value = value.strip()
    if not value:
        return "(direct)"
    parsed = urlsplit(value)
    return (parsed.hostname or value)[:512]
