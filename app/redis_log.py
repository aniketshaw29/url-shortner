import logging
import time

logger = logging.getLogger(__name__)

_LAST_LOGGED: dict[str, float] = {}
_INTERVAL_SECONDS = 10.0


def log_redis_error(message: str, exc: Exception) -> None:
    now = time.monotonic()
    if now - _LAST_LOGGED.get(message, 0.0) < _INTERVAL_SECONDS:
        return
    _LAST_LOGGED[message] = now
    logger.warning("%s: %s", message, exc)
