import base64
import json
from datetime import UTC, date, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, Response
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.analytics import visitor_key
from app.cache import invalidate_link
from app.codes import generate_code, is_reserved_alias, is_valid_alias
from app.db import get_db
from app.errors import APIError
from app.models import Link, LinkDailyStat, LinkReferrerDailyStat
from app.rate_limit import RateLimitResult, check_rate_limit, rate_limit_headers
from app.schemas import (
    LinkCreate,
    LinkDetailResponse,
    LinkListItem,
    LinkListResponse,
    LinkResponse,
    ReferrerStat,
    StatsPoint,
    StatsRange,
    StatsResponse,
)
from app.security import api_key_identity, require_api_key
from app.timeutils import datetime_to_ts, day_string, ts_to_datetime, utc_now_ts

router = APIRouter(prefix="/api/v1", tags=["links"])

MAX_STATS_DAYS = 366


def _enforce_rate_limit(request: Request, api_key: str, scope: str, limit: int) -> RateLimitResult:
    redis_client = request.app.state.redis
    identity = api_key_identity(api_key)
    result = check_rate_limit(redis_client, f"ratelimit:{scope}:{identity}", limit)
    if not result.allowed:
        headers = rate_limit_headers(result)
        headers["Retry-After"] = str(result.reset_seconds)
        raise APIError(429, "rate_limited", "Too many requests", headers=headers)
    return result


def _get_link(db: Session, code: str, include_deleted: bool = True) -> Link:
    link = db.scalar(select(Link).where(Link.code == code))
    if link is None or (not include_deleted and link.status == "deleted"):
        raise APIError(404, "not_found", "Short code does not exist")
    return link


def _total_clicks(db: Session, link_id: int) -> int:
    value = db.scalar(
        select(func.coalesce(func.sum(LinkDailyStat.clicks), 0)).where(
            LinkDailyStat.link_id == link_id
        )
    )
    return int(value or 0)


def _encode_cursor(link_id: int) -> str:
    return base64.urlsafe_b64encode(json.dumps({"id": link_id}).encode()).decode()


def _decode_cursor(value: str) -> int:
    try:
        payload = json.loads(base64.urlsafe_b64decode(value.encode()))
        return int(payload["id"])
    except (ValueError, KeyError, json.JSONDecodeError) as exc:
        raise APIError(400, "invalid_cursor", "Cursor is invalid") from exc


def _link_response(link: Link, base_url: str) -> LinkResponse:
    return LinkResponse(
        code=link.code,
        short_url=f"{base_url.rstrip('/')}/{link.code}",
        long_url=link.long_url,
        created_at=ts_to_datetime(link.created_at),
        expires_at=ts_to_datetime(link.expires_at) if link.expires_at else None,
    )


def _visitor_count(redis_client: object, link_id: int, days: list[str]) -> int:
    if not days:
        return 0
    keys = [visitor_key(link_id, day) for day in days]
    try:
        return int(redis_client.pfcount(*keys))  # type: ignore[attr-defined]
    except Exception:
        return 0


def _days_between(from_day: str, to_day: str) -> list[str]:
    start = date.fromisoformat(from_day)
    end = date.fromisoformat(to_day)
    if (end - start).days > MAX_STATS_DAYS:
        raise APIError(400, "invalid_range", f"Range must be at most {MAX_STATS_DAYS} days")
    day_count = (end - start).days + 1
    return [(start + timedelta(days=offset)).isoformat() for offset in range(day_count)]


@router.post("/links", response_model=LinkResponse, status_code=201)
def create_link(
    payload: LinkCreate,
    request: Request,
    response: Response,
    api_key: Annotated[str, Depends(require_api_key)],
    db: Annotated[Session, Depends(get_db)],
) -> LinkResponse:
    settings = request.app.state.settings
    rate = _enforce_rate_limit(request, api_key, "create", settings.rate_limit_create_per_minute)

    custom_alias = payload.custom_alias
    if custom_alias is not None:
        if not is_valid_alias(custom_alias):
            raise APIError(400, "invalid_alias", "Alias must be 3-30 chars of [a-z0-9_-]")
        if is_reserved_alias(custom_alias):
            raise APIError(422, "alias_reserved", "This alias is reserved")

    expires_at: int | None = None
    if payload.expires_at is not None:
        expires_at = datetime_to_ts(payload.expires_at)
        if expires_at <= utc_now_ts():
            raise APIError(400, "invalid_expiry", "expires_at must be in the future")

    for attempt in range(5):
        code = custom_alias or generate_code()
        link = Link(
            code=code,
            long_url=payload.long_url,
            status="active",
            expires_at=expires_at,
        )
        db.add(link)
        try:
            db.commit()
        except IntegrityError as exc:
            db.rollback()
            if custom_alias is not None:
                raise APIError(409, "alias_taken", "Custom alias is already in use") from exc
            if attempt == 4:
                raise APIError(500, "internal_error", "Could not allocate a short code") from exc
            continue

        invalidate_link(request.app.state.redis, code)
        response.headers.update(rate_limit_headers(rate))
        return _link_response(link, settings.base_url)

    raise APIError(500, "internal_error", "Could not allocate a short code")


@router.get("/links", response_model=LinkListResponse)
def list_links(
    request: Request,
    response: Response,
    api_key: Annotated[str, Depends(require_api_key)],
    db: Annotated[Session, Depends(get_db)],
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    cursor: str | None = None,
    status: Annotated[str | None, Query(pattern="^(active|expired|deleted)$")] = None,
) -> LinkListResponse:
    settings = request.app.state.settings
    rate = _enforce_rate_limit(request, api_key, "read", settings.rate_limit_api_per_minute)

    statement = select(Link).order_by(Link.id.desc()).limit(limit + 1)
    if cursor:
        statement = statement.where(Link.id < _decode_cursor(cursor))
    if status == "expired":
        statement = statement.where(
            Link.status == "active",
            Link.expires_at.is_not(None),
            Link.expires_at <= utc_now_ts(),
        )
    elif status is not None:
        statement = statement.where(Link.status == status)

    rows = list(db.scalars(statement))
    has_more = len(rows) > limit
    rows = rows[:limit]
    items = [
        LinkListItem(
            code=link.code,
            long_url=link.long_url,
            created_at=ts_to_datetime(link.created_at),
            total_clicks=_total_clicks(db, link.id),
        )
        for link in rows
    ]
    next_cursor = _encode_cursor(rows[-1].id) if has_more and rows else None
    response.headers.update(rate_limit_headers(rate))
    return LinkListResponse(items=items, next_cursor=next_cursor)


@router.get("/links/{code}", response_model=LinkDetailResponse)
def get_link(
    code: str,
    request: Request,
    response: Response,
    api_key: Annotated[str, Depends(require_api_key)],
    db: Annotated[Session, Depends(get_db)],
) -> LinkDetailResponse:
    settings = request.app.state.settings
    rate = _enforce_rate_limit(request, api_key, "read", settings.rate_limit_api_per_minute)
    link = _get_link(db, code)
    response.headers.update(rate_limit_headers(rate))
    base = _link_response(link, settings.base_url)
    return LinkDetailResponse(
        **base.model_dump(),
        status=link.status,
        total_clicks=_total_clicks(db, link.id),
    )


@router.delete("/links/{code}", status_code=204)
def delete_link(
    code: str,
    request: Request,
    api_key: Annotated[str, Depends(require_api_key)],
    db: Annotated[Session, Depends(get_db)],
) -> Response:
    settings = request.app.state.settings
    rate = _enforce_rate_limit(request, api_key, "write", settings.rate_limit_api_per_minute)
    link = _get_link(db, code)
    if link.status != "deleted":
        now = utc_now_ts()
        link.status = "deleted"
        link.deleted_at = now
        link.updated_at = now
        db.commit()
    invalidate_link(request.app.state.redis, code)
    return Response(status_code=204, headers=rate_limit_headers(rate))


@router.get("/links/{code}/stats", response_model=StatsResponse)
def get_stats(
    code: str,
    request: Request,
    response: Response,
    api_key: Annotated[str, Depends(require_api_key)],
    db: Annotated[Session, Depends(get_db)],
    from_: Annotated[datetime | None, Query(alias="from")] = None,
    to: datetime | None = None,
    interval: Annotated[str, Query(pattern="^day$")] = "day",
) -> StatsResponse:
    del interval
    settings = request.app.state.settings
    rate = _enforce_rate_limit(request, api_key, "read", settings.rate_limit_api_per_minute)
    link = _get_link(db, code)

    now = datetime.now(UTC)
    to_dt = to or now
    from_dt = from_ or (to_dt - timedelta(days=30))
    if from_dt.tzinfo is None:
        from_dt = from_dt.replace(tzinfo=UTC)
    if to_dt.tzinfo is None:
        to_dt = to_dt.replace(tzinfo=UTC)
    if from_dt > to_dt:
        raise APIError(400, "invalid_range", "from must be before to")

    from_day = day_string(datetime_to_ts(from_dt))
    to_day = day_string(datetime_to_ts(to_dt))
    days = _days_between(from_day, to_day)

    daily_rows = list(
        db.scalars(
            select(LinkDailyStat)
            .where(
                LinkDailyStat.link_id == link.id,
                LinkDailyStat.day >= from_day,
                LinkDailyStat.day <= to_day,
            )
            .order_by(LinkDailyStat.day)
        )
    )
    series = [
        StatsPoint(
            bucket=row.day,
            clicks=row.clicks,
            unique_visitors=_visitor_count(request.app.state.redis, link.id, [row.day]),
        )
        for row in daily_rows
    ]

    referrer_rows = list(
        db.execute(
            select(
                LinkReferrerDailyStat.referrer,
                func.sum(LinkReferrerDailyStat.clicks).label("clicks"),
            )
            .where(
                LinkReferrerDailyStat.link_id == link.id,
                LinkReferrerDailyStat.day >= from_day,
                LinkReferrerDailyStat.day <= to_day,
            )
            .group_by(LinkReferrerDailyStat.referrer)
            .order_by(func.sum(LinkReferrerDailyStat.clicks).desc())
            .limit(10)
        )
    )

    response.headers.update(rate_limit_headers(rate))
    return StatsResponse(
        code=link.code,
        range=StatsRange.model_validate({"from": from_dt, "to": to_dt}),
        total_clicks=sum(row.clicks for row in daily_rows),
        unique_visitors=_visitor_count(request.app.state.redis, link.id, days),
        series=series,
        top_referrers=[
            ReferrerStat(referrer=referrer, clicks=int(clicks))
            for referrer, clicks in referrer_rows
        ],
    )
