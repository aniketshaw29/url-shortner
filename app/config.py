from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_env: str = "local"
    base_url: str = "http://localhost:8000"
    database_url: str = "sqlite:///./data/app.db"
    redis_url: str = "redis://localhost:6379/0"
    api_key: str = "dev-api-key"
    ip_hash_salt: str = "local-dev-salt"
    cache_ttl_seconds: int = 3600
    analytics_worker_enabled: bool = True
    analytics_stream: str = "events:clicks"
    analytics_group: str = "analytics"
    analytics_consumer: str = "worker-1"
    rate_limit_redirect_per_minute: int = 600
    rate_limit_api_per_minute: int = 300
    rate_limit_create_per_minute: int = 30
    log_level: str = "INFO"


@lru_cache
def get_settings() -> Settings:
    return Settings()
