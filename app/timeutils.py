from datetime import UTC, datetime


def utc_now_ts() -> int:
    return int(datetime.now(UTC).timestamp())


def ts_to_datetime(value: int) -> datetime:
    return datetime.fromtimestamp(value, tz=UTC)


def datetime_to_ts(value: datetime) -> int:
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return int(value.timestamp())


def day_string(value: int) -> str:
    return datetime.fromtimestamp(value, tz=UTC).strftime("%Y-%m-%d")
