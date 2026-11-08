import sqlite3
from collections.abc import Iterator
from pathlib import Path

from fastapi import Request
from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.engine.interfaces import ExceptionContext
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.metrics import SQLITE_BUSY


class Base(DeclarativeBase):
    pass


def _ensure_sqlite_directory(database_url: str) -> None:
    if not database_url.startswith("sqlite:///") or ":memory:" in database_url:
        return
    path = Path(database_url.removeprefix("sqlite:///")).expanduser()
    path.resolve().parent.mkdir(parents=True, exist_ok=True)


def count_sqlite_busy(exception_context: ExceptionContext) -> None:
    exc = exception_context.original_exception
    if isinstance(exc, sqlite3.OperationalError) and "database is locked" in str(exc):
        SQLITE_BUSY.inc()


def create_db_engine(database_url: str) -> Engine:
    _ensure_sqlite_directory(database_url)
    engine = create_engine(
        database_url,
        connect_args={"check_same_thread": False},
        pool_pre_ping=True,
    )

    if engine.dialect.name == "sqlite":
        event.listen(engine, "handle_error", count_sqlite_busy)

        @event.listens_for(engine, "connect")
        def set_sqlite_pragmas(dbapi_connection: object, _connection_record: object) -> None:
            cursor = dbapi_connection.cursor()  # type: ignore[attr-defined]
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.execute("PRAGMA busy_timeout=5000")
            cursor.execute("PRAGMA synchronous=NORMAL")
            cursor.close()

    return engine


def create_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db(request: Request) -> Iterator[Session]:
    session = request.app.state.session_factory()
    try:
        yield session
    finally:
        session.close()
