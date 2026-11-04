import json
import logging
import random
from typing import Any

from redis import Redis
from redis.exceptions import RedisError

logger = logging.getLogger(__name__)

LINK_KEY = "link:{code}"
MISS_KEY = "link:miss:{code}"
NEGATIVE_TTL_SECONDS = 45


def get_cached_link(redis_client: Redis, code: str) -> tuple[bool, dict[str, Any] | None]:
    try:
        raw = redis_client.get(LINK_KEY.format(code=code))
        if raw:
            return True, json.loads(raw)
        if redis_client.exists(MISS_KEY.format(code=code)):
            return True, None
    except (RedisError, json.JSONDecodeError):
        logger.warning("cache read failed", exc_info=True)
    return False, None


def set_cached_link(
    redis_client: Redis, code: str, payload: dict[str, Any], ttl_seconds: int
) -> None:
    try:
        ttl = ttl_seconds + random.randint(0, 300)
        redis_client.set(LINK_KEY.format(code=code), json.dumps(payload), ex=ttl)
    except RedisError:
        logger.warning("cache write failed", exc_info=True)


def set_negative_cache(redis_client: Redis, code: str) -> None:
    try:
        redis_client.set(MISS_KEY.format(code=code), "1", ex=NEGATIVE_TTL_SECONDS)
    except RedisError:
        logger.warning("negative cache write failed", exc_info=True)


def invalidate_link(redis_client: Redis, code: str) -> None:
    try:
        redis_client.delete(LINK_KEY.format(code=code), MISS_KEY.format(code=code))
    except RedisError:
        logger.warning("cache invalidation failed", exc_info=True)
