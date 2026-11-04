import logging
from dataclasses import dataclass

from redis import Redis
from redis.exceptions import RedisError

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RateLimitResult:
    allowed: bool
    limit: int
    remaining: int
    reset_seconds: int


def check_rate_limit(
    redis_client: Redis, key: str, limit: int, window_seconds: int = 60
) -> RateLimitResult:
    try:
        current = redis_client.incr(key)
        if current == 1:
            redis_client.expire(key, window_seconds)
        ttl = redis_client.ttl(key)
        if ttl is None or ttl < 0:
            ttl = window_seconds
        return RateLimitResult(
            allowed=current <= limit,
            limit=limit,
            remaining=max(0, limit - current),
            reset_seconds=int(ttl),
        )
    except RedisError:
        logger.warning("rate limiter unavailable; failing open", exc_info=True)
        return RateLimitResult(
            allowed=True, limit=limit, remaining=limit, reset_seconds=window_seconds
        )


def rate_limit_headers(result: RateLimitResult) -> dict[str, str]:
    return {
        "RateLimit-Limit": str(result.limit),
        "RateLimit-Remaining": str(result.remaining),
        "RateLimit-Reset": str(result.reset_seconds),
    }
