from datetime import UTC, datetime, timedelta

import fakeredis
from fastapi.testclient import TestClient
from redis.exceptions import RedisError
from sqlalchemy import select

from app.db import Base
from app.main import create_app
from app.models import Link, LinkDailyStat, LinkReferrerDailyStat
from app.timeutils import utc_now_ts


class BrokenRedis:
    def __init__(self) -> None:
        self.calls = 0

    def incr(self, *_args, **_kwargs):
        self.calls += 1
        raise RedisError("redis down")

    def get(self, *_args, **_kwargs):
        raise RedisError("redis down")

    def exists(self, *_args, **_kwargs):
        raise RedisError("redis down")

    def set(self, *_args, **_kwargs):
        raise RedisError("redis down")

    def delete(self, *_args, **_kwargs):
        raise RedisError("redis down")

    def xadd(self, *_args, **_kwargs):
        raise RedisError("redis down")


def _create(client: TestClient, headers: dict[str, str], **payload):
    body = {"long_url": "https://example.com/a/long/path"}
    body.update(payload)
    return client.post("/api/v1/links", json=body, headers=headers)


def test_create_and_redirect(client: TestClient, auth_headers: dict[str, str]) -> None:
    response = _create(client, auth_headers)
    assert response.status_code == 201
    data = response.json()
    assert len(data["code"]) == 7
    assert data["short_url"].endswith(data["code"])
    assert data["long_url"] == "https://example.com/a/long/path"

    redirect_response = client.get(f"/{data['code']}", follow_redirects=False)
    assert redirect_response.status_code == 302
    assert redirect_response.headers["location"] == "https://example.com/a/long/path"
    assert redirect_response.headers["cache-control"] == "no-store"


def test_redirect_rate_limit_key_hashes_ip(
    client: TestClient, application, auth_headers: dict[str, str]
) -> None:
    created = _create(client, auth_headers).json()
    client.get(f"/{created['code']}", follow_redirects=False)

    keys = application.state.redis.keys("ratelimit:redirect:*")
    assert keys
    assert all("testclient" not in key for key in keys)
    assert all("127.0.0.1" not in key for key in keys)


def test_redirect_survives_redis_outage(
    client: TestClient, application, auth_headers: dict[str, str]
) -> None:
    created = _create(client, auth_headers).json()
    broken = BrokenRedis()
    application.state.redis = broken

    first = client.get(f"/{created['code']}", follow_redirects=False)
    second = client.get(f"/{created['code']}", follow_redirects=False)

    assert first.status_code == 302
    assert second.status_code == 302
    assert broken.calls == 1


def test_create_requires_api_key(client: TestClient) -> None:
    response = client.post("/api/v1/links", json={"long_url": "https://example.com/a/long/path"})
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthorized"


def test_invalid_url_rejected(client: TestClient, auth_headers: dict[str, str]) -> None:
    response = _create(client, auth_headers, long_url="javascript:alert(1)")
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_request"


def test_custom_alias_and_conflict(client: TestClient, auth_headers: dict[str, str]) -> None:
    first = _create(client, auth_headers, custom_alias="Launch-2026")
    assert first.status_code == 201
    assert first.json()["code"] == "launch-2026"

    second = _create(client, auth_headers, custom_alias="launch-2026")
    assert second.status_code == 409
    assert second.json()["error"]["code"] == "alias_taken"


def test_reserved_alias(client: TestClient, auth_headers: dict[str, str]) -> None:
    response = _create(client, auth_headers, custom_alias="healthz")
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "alias_reserved"


def test_expired_link_returns_gone(
    client: TestClient, application, auth_headers: dict[str, str]
) -> None:
    with application.state.session_factory() as session:
        link = Link(
            code="expired1",
            long_url="https://example.com/expired",
            expires_at=utc_now_ts() - 10,
        )
        session.add(link)
        session.commit()

    response = client.get("/expired1", follow_redirects=False)
    assert response.status_code == 410
    assert response.json()["error"]["code"] == "gone"


def test_delete_is_idempotent_and_invalidates_cache(
    client: TestClient, application, auth_headers: dict[str, str]
) -> None:
    created = _create(client, auth_headers, custom_alias="delete-me").json()
    code = created["code"]

    assert client.get(f"/{code}", follow_redirects=False).status_code == 302
    assert application.state.redis.get(f"link:{code}") is not None

    assert client.delete(f"/api/v1/links/{code}", headers=auth_headers).status_code == 204
    assert application.state.redis.get(f"link:{code}") is None
    assert client.get(f"/{code}", follow_redirects=False).status_code == 410
    assert client.delete(f"/api/v1/links/{code}", headers=auth_headers).status_code == 204


def test_metadata_and_list(client: TestClient, auth_headers: dict[str, str]) -> None:
    created = _create(client, auth_headers, custom_alias="meta-link").json()

    detail = client.get(f"/api/v1/links/{created['code']}", headers=auth_headers)
    assert detail.status_code == 200
    assert detail.json()["status"] == "active"

    listing = client.get("/api/v1/links", headers=auth_headers)
    assert listing.status_code == 200
    assert any(item["code"] == "meta-link" for item in listing.json()["items"])


def test_stats_aggregates_rollups(
    client: TestClient, application, auth_headers: dict[str, str]
) -> None:
    created = _create(client, auth_headers, custom_alias="stats-link").json()
    code = created["code"]

    with application.state.session_factory() as session:
        link = session.scalar(select(Link).where(Link.code == code))
        assert link is not None
        day = datetime.now(UTC).strftime("%Y-%m-%d")
        session.add(LinkDailyStat(link_id=link.id, day=day, clicks=5))
        session.add(
            LinkReferrerDailyStat(link_id=link.id, day=day, referrer="news.example.com", clicks=3)
        )
        session.commit()

    response = client.get(f"/api/v1/links/{code}/stats", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["total_clicks"] == 5
    assert data["series"][0]["clicks"] == 5
    assert data["top_referrers"][0]["referrer"] == "news.example.com"


def test_readyz(client: TestClient) -> None:
    response = client.get("/readyz")
    assert response.status_code == 200
    assert response.json() == {"status": "ready"}


def test_rate_limit(settings) -> None:
    limited = settings.model_copy(update={"rate_limit_create_per_minute": 1})
    app = create_app(limited)
    Base.metadata.create_all(app.state.engine)
    headers = {"Authorization": "Bearer test-key"}

    with TestClient(app) as client:
        app.state.redis = fakeredis.FakeRedis(decode_responses=True)
        first = _create(client, headers)
        second = _create(client, headers)

    assert first.status_code == 201
    assert second.status_code == 429
    assert second.json()["error"]["code"] == "rate_limited"
    assert "Retry-After" in second.headers


def test_metrics_endpoint(client: TestClient, auth_headers: dict[str, str]) -> None:
    created = _create(client, auth_headers).json()
    client.get(f"/{created['code']}", follow_redirects=False)

    response = client.get("/metrics")

    assert response.status_code == 200
    assert "shortener_http_requests_total" in response.text
    assert "shortener_cache_operations_total" in response.text
    assert "shortener_redirects_total" in response.text


def test_redirect_rate_limit(settings, auth_headers: dict[str, str]) -> None:
    limited = settings.model_copy(update={"rate_limit_redirect_per_minute": 1})
    app = create_app(limited)
    Base.metadata.create_all(app.state.engine)

    with TestClient(app) as client:
        app.state.redis = fakeredis.FakeRedis(decode_responses=True)
        code = _create(client, auth_headers).json()["code"]
        first = client.get(f"/{code}", follow_redirects=False)
        second = client.get(f"/{code}", follow_redirects=False)

    assert first.status_code == 302
    assert second.status_code == 429
    assert second.json()["error"]["code"] == "rate_limited"
    assert "Retry-After" in second.headers


def test_expiry_in_the_past_rejected(client: TestClient, auth_headers: dict[str, str]) -> None:
    past = (datetime.now(UTC) - timedelta(minutes=1)).isoformat()
    response = _create(client, auth_headers, expires_at=past)
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_expiry"
