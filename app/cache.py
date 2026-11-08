import json
import logging
import random
import threading
from typing import Any

from redis import Redis
from redis.exceptions import RedisError

from app.metrics import CACHE_OPERATIONS
from app.redis_log import log_redis_error
from app.redis_state import (
    allow_redis_call,
    consume_cache_flush,
    record_redis_failure,
    record_redis_success,
    request_cache_flush,
)

logger = logging.getLogger(__name__)

LINK_KEY = "link:{code}"
MISS_KEY = "link:miss:{code}"
NEGATIVE_TTL_SECONDS = 45
_pending_lock = threading.Lock()
_pending_invalidations: set[str] = set()


def get_cached_link(redis_client: Redis, code: str) -> tuple[bool, dict[str, Any] | None]:
    if not allow_redis_call():
        CACHE_OPERATIONS.labels(result="skipped").inc()
        return False, None
    if consume_cache_flush():
        _flush_pending_invalidations(redis_client)
        CACHE_OPERATIONS.labels(result="recovery").inc()
        return False, None
    try:
        raw = redis_client.get(LINK_KEY.format(code=code))
        negative = False if raw else redis_client.exists(MISS_KEY.format(code=code))
    except RedisError as exc:
        record_redis_failure()
        CACHE_OPERATIONS.labels(result="error").inc()
        log_redis_error("cache read failed", exc)
        return False, None
    record_redis_success()
    if consume_cache_flush():
        _flush_pending_invalidations(redis_client)
        CACHE_OPERATIONS.labels(result="recovery").inc()
        return False, None
    if raw:
        try:
            CACHE_OPERATIONS.labels(result="hit").inc()
            return True, json.loads(raw)
        except json.JSONDecodeError:
            CACHE_OPERATIONS.labels(result="error").inc()
            logger.warning("cache payload invalid", exc_info=True)
            return False, None
    if negative:
        CACHE_OPERATIONS.labels(result="negative").inc()
        return True, None
    CACHE_OPERATIONS.labels(result="miss").inc()
    return False, None


def set_cached_link(
    redis_client: Redis, code: str, payload: dict[str, Any], ttl_seconds: int
) -> None:
    if not allow_redis_call():
        return
    try:
        ttl = ttl_seconds + random.randint(0, 300)
        redis_client.set(LINK_KEY.format(code=code), json.dumps(payload), ex=ttl)
    except RedisError as exc:
        record_redis_failure()
        log_redis_error("cache write failed", exc)
    else:
        record_redis_success()


def set_negative_cache(redis_client: Redis, code: str) -> None:
    if not allow_redis_call():
        return
    try:
        redis_client.set(MISS_KEY.format(code=code), "1", ex=NEGATIVE_TTL_SECONDS)
    except RedisError as exc:
        record_redis_failure()
        log_redis_error("negative cache write failed", exc)
    else:
        record_redis_success()


def invalidate_link(redis_client: Redis, code: str) -> None:
    if not allow_redis_call():
        _remember_invalidation(code)
        return
    try:
        redis_client.delete(LINK_KEY.format(code=code), MISS_KEY.format(code=code))
    except RedisError as exc:
        _remember_invalidation(code)
        record_redis_failure()
        log_redis_error("cache invalidation failed", exc)
    else:
        record_redis_success()


def reset_pending_invalidations() -> None:
    with _pending_lock:
        _pending_invalidations.clear()


def _remember_invalidation(code: str) -> None:
    with _pending_lock:
        _pending_invalidations.add(code)


def _flush_pending_invalidations(redis_client: Redis) -> None:
    with _pending_lock:
        codes = list(_pending_invalidations)
        _pending_invalidations.clear()
    if not codes:
        return
    try:
        pipeline = redis_client.pipeline()
        for code in codes:
            pipeline.delete(LINK_KEY.format(code=code), MISS_KEY.format(code=code))
        pipeline.execute()
    except RedisError as exc:
        with _pending_lock:
            _pending_invalidations.update(codes)
        request_cache_flush()
        record_redis_failure()
        log_redis_error("cache recovery flush failed", exc)
