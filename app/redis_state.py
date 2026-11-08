import threading
import time

_CLOSED = "closed"
_OPEN = "open"
_HALF_OPEN = "half_open"
_COOLDOWN_SECONDS = 5.0

_lock = threading.Lock()
_state = _CLOSED
_open_until = 0.0
_cache_flush_needed = False


def allow_redis_call() -> bool:
    global _state
    now = time.monotonic()
    with _lock:
        if _state == _CLOSED:
            return True
        if _state == _OPEN:
            if now < _open_until:
                return False
            _state = _HALF_OPEN
            return True
        return False


def record_redis_success() -> bool:
    global _state, _open_until, _cache_flush_needed
    with _lock:
        transitioned = _state != _CLOSED
        if transitioned:
            _cache_flush_needed = True
        _state = _CLOSED
        _open_until = 0.0
        return transitioned


def consume_cache_flush() -> bool:
    global _cache_flush_needed
    with _lock:
        needed = _cache_flush_needed
        _cache_flush_needed = False
        return needed


def request_cache_flush() -> None:
    global _cache_flush_needed
    with _lock:
        _cache_flush_needed = True


def record_redis_failure() -> None:
    global _state, _open_until
    with _lock:
        _state = _OPEN
        _open_until = time.monotonic() + _COOLDOWN_SECONDS


def reset_redis_state() -> None:
    global _state, _open_until, _cache_flush_needed
    with _lock:
        _state = _CLOSED
        _open_until = 0.0
        _cache_flush_needed = False
