"""Alembic migration helpers and package for ADME storage."""

from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config as AlembicConfig
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy.engine import make_url

from app.storage.config import StorageConfig
from app.storage.engine import create_engine_from_config

ALEMBIC_INI_PATH = Path(__file__).resolve().parents[3] / "alembic.ini"
MIGRATIONS_PATH = Path(__file__).resolve().parent


class StorageMigrationError(RuntimeError):
    """Raised when storage migrations or revision checks fail safely."""


def run_sqlite_migrations(config: StorageConfig) -> None:
    """Apply Alembic migrations for local SQLite development storage."""
    if config.backend != "sqlite":
        raise StorageMigrationError("SQLite auto-migration only supports SQLite.")

    try:
        _prepare_sqlite_database_path(config)
        command.upgrade(_alembic_config(config), "head")
    except Exception as exc:
        raise StorageMigrationError(
            f"SQLite migration failed for {config.safe_description}: "
            f"{type(exc).__name__}"
        ) from None


def ensure_storage_ready(config: StorageConfig) -> None:
    """Prepare SQLite storage or verify PostgreSQL is already migrated."""
    if config.backend == "sqlite":
        run_sqlite_migrations(config)
        return

    current_revision = _current_database_revision(config)
    expected_revision = _expected_head_revision(config)
    if current_revision != expected_revision:
        current_label = current_revision or "uninitialized"
        raise StorageMigrationError(
            "PostgreSQL storage is not at the expected Alembic revision "
            f"({current_label} != {expected_revision}). Run migrations before "
            "starting the app."
        )


def _alembic_config(config: StorageConfig) -> AlembicConfig:
    alembic_config = AlembicConfig(str(ALEMBIC_INI_PATH))
    alembic_config.set_main_option("script_location", str(MIGRATIONS_PATH))
    alembic_config.set_main_option("sqlalchemy.url", config.url)
    alembic_config.attributes["storage_database_url"] = config.url
    return alembic_config


def _expected_head_revision(config: StorageConfig) -> str:
    try:
        head = ScriptDirectory.from_config(_alembic_config(config)).get_current_head()
    except Exception as exc:
        raise StorageMigrationError(
            f"Could not read expected migration head: {type(exc).__name__}"
        ) from None
    if head is None:
        raise StorageMigrationError("No Alembic head revision is configured.")
    return head


def _current_database_revision(config: StorageConfig) -> str | None:
    try:
        engine = create_engine_from_config(config)
        try:
            with engine.connect() as connection:
                context = MigrationContext.configure(connection)
                return context.get_current_revision()
        finally:
            engine.dispose()
    except Exception as exc:
        raise StorageMigrationError(
            f"Storage revision check failed for {config.safe_description}: "
            f"{type(exc).__name__}"
        ) from None


def _prepare_sqlite_database_path(config: StorageConfig) -> None:
    database = make_url(config.url).database
    if database is None or database == ":memory:":
        return
    Path(database).parent.mkdir(parents=True, exist_ok=True)
