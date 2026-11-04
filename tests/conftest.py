import fakeredis
import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.db import Base
from app.main import create_app


@pytest.fixture()
def settings(tmp_path) -> Settings:
    return Settings(
        app_env="test",
        base_url="http://testserver",
        database_url=f"sqlite:///{tmp_path / 'test.db'}",
        redis_url="redis://localhost:6379/15",
        api_key="test-key",
        ip_hash_salt="test-salt",
        cache_ttl_seconds=60,
        analytics_worker_enabled=False,
        rate_limit_redirect_per_minute=1000,
        rate_limit_api_per_minute=1000,
        rate_limit_create_per_minute=1000,
    )


@pytest.fixture()
def application(settings):
    app = create_app(settings)
    Base.metadata.create_all(app.state.engine)
    return app


@pytest.fixture()
def client(application):
    with TestClient(application) as test_client:
        application.state.redis = fakeredis.FakeRedis(decode_responses=True)
        yield test_client


@pytest.fixture()
def auth_headers() -> dict[str, str]:
    return {"Authorization": "Bearer test-key"}
