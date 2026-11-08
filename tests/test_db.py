import sqlite3
from types import SimpleNamespace

from prometheus_client import REGISTRY

from app.db import count_sqlite_busy


def _busy_count() -> float:
    return REGISTRY.get_sample_value("shortener_sqlite_busy_total") or 0.0


def test_sqlite_busy_metric_increments() -> None:
    before = _busy_count()
    count_sqlite_busy(
        SimpleNamespace(original_exception=sqlite3.OperationalError("database is locked"))
    )
    assert _busy_count() == before + 1


def test_sqlite_busy_metric_ignores_other_errors() -> None:
    before = _busy_count()
    count_sqlite_busy(SimpleNamespace(original_exception=sqlite3.OperationalError("no such table")))
    assert _busy_count() == before
