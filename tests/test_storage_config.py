"""Tests for storage configuration resolution and redaction."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.storage.config import resolve_storage_config


def test_default_storage_config_uses_local_sqlite(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    base_path = tmp_path / "config-default"

    config = resolve_storage_config(base_path=base_path)

    assert config.backend == "sqlite"
    assert config.url.startswith("sqlite:///")
    assert config.url.endswith("/.adme/adme.db")
    assert ".adme" in config.safe_description


def test_postgresql_description_redacts_credentials() -> None:
    database_url = (
        "postgresql+psycopg://operator:super-secret@db.example:5432/adme"
        "?sslmode=require"
    )

    config = resolve_storage_config(database_url=database_url)

    assert config.backend == "postgresql"
    assert config.url == database_url
    assert "db.example:5432/adme" in config.safe_description
    assert "operator" not in config.safe_description
    assert "super-secret" not in config.safe_description
    assert "super-secret" not in repr(config)


def test_invalid_database_url_does_not_fallback_to_sqlite() -> None:
    with pytest.raises(ValueError, match="valid SQLAlchemy URL"):
        resolve_storage_config(database_url="not-a-url")


def test_unsupported_database_url_does_not_fallback_to_sqlite() -> None:
    with pytest.raises(ValueError, match="SQLite or PostgreSQL"):
        resolve_storage_config(database_url="mysql://user:secret@db.example/adme")
