import threading
import time

_CLOSED = "closed"
_OPEN = "open"
_HALF_OPEN = "half_open"
_COOLDOWN_SECONDS = 5.0

_lock = threading.Lock()
_state = _CLOSED
_open_until = 0.0


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


def record_redis_success() -> None:
    global _state, _open_until
    with _lock:
        _state = _CLOSED
        _open_until = 0.0


def record_redis_failure() -> None:
    global _state, _open_until
    with _lock:
        _state = _OPEN
        _open_until = time.monotonic() + _COOLDOWN_SECONDS


def reset_redis_state() -> None:
    global _state, _open_until
    with _lock:
        _state = _CLOSED
        _open_until = 0.0
