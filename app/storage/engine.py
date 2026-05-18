"""SQLAlchemy engine construction for supported storage backends."""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.engine.interfaces import DBAPIConnection
from sqlalchemy.pool import ConnectionPoolEntry, NullPool

from app.storage.config import StorageConfig


def create_engine_from_config(config: StorageConfig) -> Engine:
    """Create an Engine with backend-specific safety settings."""
    if config.backend == "sqlite":
        database_path = _sqlite_database_path(config.url)
        if database_path is not None:
            database_path.parent.mkdir(parents=True, exist_ok=True)
        if database_path is not None:
            engine = create_engine(
                config.url,
                connect_args={"check_same_thread": False},
                future=True,
                poolclass=NullPool,
            )
        else:
            engine = create_engine(
                config.url,
                connect_args={"check_same_thread": False},
                future=True,
            )
        _install_sqlite_pragmas(engine, file_backed=database_path is not None)
        return engine

    return create_engine(config.url, pool_pre_ping=True, future=True)


def _sqlite_database_path(database_url: str) -> Path | None:
    database = make_url(database_url).database
    if database is None or database == ":memory:":
        return None
    return Path(database)


def _install_sqlite_pragmas(engine: Engine, *, file_backed: bool) -> None:
    @event.listens_for(engine, "connect")
    def _set_sqlite_pragmas(
        dbapi_connection: DBAPIConnection,
        _connection_record: ConnectionPoolEntry,
    ) -> None:
        cursor = dbapi_connection.cursor()
        try:
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.execute("PRAGMA busy_timeout=5000")
            if file_backed:
                cursor.execute("PRAGMA journal_mode=WAL")
        finally:
            cursor.close()
