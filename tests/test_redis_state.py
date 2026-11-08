from app import redis_state


def test_circuit_breaker_opens_and_half_opens(monkeypatch) -> None:
    now = [100.0]
    monkeypatch.setattr(redis_state.time, "monotonic", lambda: now[0])

    assert redis_state.allow_redis_call()

    redis_state.record_redis_failure()
    assert not redis_state.allow_redis_call()

    now[0] += 6.0
    assert redis_state.allow_redis_call()
    assert not redis_state.allow_redis_call()

    redis_state.record_redis_success()
    assert redis_state.allow_redis_call()
