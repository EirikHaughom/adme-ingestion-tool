"""Storage configuration resolution and safe descriptions."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError

StorageBackend = Literal["sqlite", "postgresql"]
DEFAULT_SQLITE_DIRECTORY = ".adme"
DEFAULT_SQLITE_FILENAME = "adme.db"


@dataclass(frozen=True)
class StorageConfig:
    """Resolved database connection settings.

    The raw URL is hidden from repr so accidental logging does not expose
    credentials embedded in operator-supplied PostgreSQL URLs.
    """

    url: str = field(repr=False)
    backend: StorageBackend
    safe_description: str

    @classmethod
    def from_env(cls) -> StorageConfig:
        """Resolve storage config from DATABASE_URL or the local SQLite default."""
        return resolve_storage_config()


def resolve_storage_config(
    database_url: str | None = None,
    base_path: Path | None = None,
) -> StorageConfig:
    """Resolve the storage URL from an explicit value, env, or local SQLite."""
    raw_url = (
        database_url
        if database_url is not None
        else os.environ.get("DATABASE_URL")
    )
    if raw_url is None or not raw_url.strip():
        db_path = _default_sqlite_path(base_path)
        return StorageConfig(
            url=_sqlite_url_for_path(db_path),
            backend="sqlite",
            safe_description=f"SQLite database at {db_path}",
        )

    return _config_from_database_url(raw_url.strip())


def load_storage_config() -> StorageConfig:
    """Compatibility alias for callers that prefer a load/get convention."""
    return resolve_storage_config()


def redact_database_url(database_url: str) -> str:
    """Return a credential-safe description for an operator-supplied URL."""
    try:
        return _config_from_database_url(database_url).safe_description
    except ValueError:
        return "Invalid storage database URL"


def _default_sqlite_path(base_path: Path | None) -> Path:
    root = base_path if base_path is not None else Path.cwd()
    return (root / DEFAULT_SQLITE_DIRECTORY / DEFAULT_SQLITE_FILENAME).resolve()


def _sqlite_url_for_path(path: Path) -> str:
    return f"sqlite:///{path.as_posix()}"


def _config_from_database_url(database_url: str) -> StorageConfig:
    try:
        url = make_url(database_url)
    except ArgumentError:
        raise ValueError(
            "DATABASE_URL must be a valid SQLAlchemy URL for SQLite or PostgreSQL."
        ) from None

    backend_name = url.get_backend_name()
    if backend_name == "sqlite":
        return StorageConfig(
            url=database_url,
            backend="sqlite",
            safe_description=_safe_sqlite_description(database_url),
        )
    if backend_name == "postgresql":
        return StorageConfig(
            url=database_url,
            backend="postgresql",
            safe_description=_safe_postgresql_description(database_url),
        )

    raise ValueError("DATABASE_URL must use SQLite or PostgreSQL.")


def _safe_sqlite_description(database_url: str) -> str:
    url = make_url(database_url)
    database = url.database or ""
    if database == ":memory:":
        return "SQLite in-memory database"
    if database:
        return f"SQLite database at {Path(database)}"
    return "SQLite database"


def _safe_postgresql_description(database_url: str) -> str:
    url = make_url(database_url)
    host = url.host or "unspecified-host"
    port = f":{url.port}" if url.port is not None else ""
    database = url.database or "unspecified-database"
    return f"PostgreSQL database via {url.drivername} at {host}{port}/{database}"
