"""Alembic environment for ADME storage migrations."""

from __future__ import annotations

from alembic import context
from sqlalchemy import engine_from_config, pool

from app.storage.config import resolve_storage_config
from app.storage.models import Base

config = context.config
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Run migrations without a live database connection."""
    context.configure(
        url=_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations with a live database connection."""
    section = config.get_section(config.config_ini_section) or {}
    section["sqlalchemy.url"] = _database_url()
    connectable = engine_from_config(
        section,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
        future=True,
    )

    try:
        with connectable.connect() as connection:
            context.configure(connection=connection, target_metadata=target_metadata)
            with context.begin_transaction():
                context.run_migrations()
    finally:
        connectable.dispose()


def _database_url() -> str:
    configured_url = config.get_main_option("sqlalchemy.url")
    if configured_url and configured_url != "__runtime_database_url__":
        return configured_url

    attribute_url = config.attributes.get("storage_database_url")
    if isinstance(attribute_url, str) and attribute_url:
        return attribute_url

    return resolve_storage_config().url


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
