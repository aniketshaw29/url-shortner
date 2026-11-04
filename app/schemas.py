from datetime import UTC, datetime
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.codes import normalize_alias


class LinkCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    long_url: str = Field(min_length=1, max_length=2048)
    custom_alias: str | None = None
    expires_at: datetime | None = None

    @field_validator("long_url")
    @classmethod
    def validate_long_url(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("long_url must not be empty")
        parsed = urlsplit(value)
        if parsed.scheme.lower() not in {"http", "https"}:
            raise ValueError("long_url must use http or https")
        if not parsed.netloc:
            raise ValueError("long_url must be absolute")
        if parsed.username or parsed.password:
            raise ValueError("long_url must not contain credentials")
        if any(char.isspace() for char in value):
            raise ValueError("long_url must not contain whitespace")
        return value

    @field_validator("custom_alias")
    @classmethod
    def normalize_custom_alias(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return normalize_alias(value)

    @field_validator("expires_at")
    @classmethod
    def ensure_expiry_timezone(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value


class LinkResponse(BaseModel):
    code: str
    short_url: str
    long_url: str
    created_at: datetime
    expires_at: datetime | None


class LinkDetailResponse(LinkResponse):
    status: str
    total_clicks: int


class LinkListItem(BaseModel):
    code: str
    long_url: str
    created_at: datetime
    total_clicks: int


class LinkListResponse(BaseModel):
    items: list[LinkListItem]
    next_cursor: str | None


class StatsPoint(BaseModel):
    bucket: str
    clicks: int
    unique_visitors: int


class ReferrerStat(BaseModel):
    referrer: str
    clicks: int


class StatsRange(BaseModel):
    from_: datetime = Field(alias="from")
    to: datetime


class StatsResponse(BaseModel):
    code: str
    range: StatsRange
    total_clicks: int
    unique_visitors: int
    series: list[StatsPoint]
    top_referrers: list[ReferrerStat]
