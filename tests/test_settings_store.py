"""Tests for the local SQLite-backed connection settings store.

Every test isolates the database via ``ADME_SETTINGS_DB`` pointing into
``tmp_path``.  Nothing in this module is allowed to touch the operator's
real ``~/.adme-ingestion-tool/`` directory.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from app.models.connection import ADME_RESOURCE_SCOPE, ADMEConnection, AuthMethod
from app.services import settings_store
from app.services.settings_store import SettingsStoreError


@pytest.fixture
def db_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point the settings store at an isolated SQLite file under tmp_path."""
    target = tmp_path / "settings.db"
    monkeypatch.setenv("ADME_SETTINGS_DB", str(target))
    return target


def _make_connection(
    *,
    endpoint: str = "https://example.energy.azure.com",
    tenant_id: str = "11111111-1111-1111-1111-111111111111",
    client_id: str = "22222222-2222-2222-2222-222222222222",
    data_partition_id: str = "example-opendes",
    token_scope: str = ADME_RESOURCE_SCOPE,
    auth_method: AuthMethod = AuthMethod.USER_IMPERSONATION,
    client_secret: str = "",
) -> ADMEConnection:
    return ADMEConnection(
        endpoint=endpoint,
        tenant_id=tenant_id,
        client_id=client_id,
        data_partition_id=data_partition_id,
        token_scope=token_scope,
        auth_method=auth_method,
        client_secret=client_secret,
    )


def test_get_db_path_honors_env_override(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "override.db"
    monkeypatch.setenv("ADME_SETTINGS_DB", str(target))

    assert settings_store.get_db_path() == target


def test_get_db_path_defaults_when_env_not_set(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("ADME_SETTINGS_DB", raising=False)

    assert settings_store.get_db_path() == settings_store.DEFAULT_DB_PATH


def test_initialize_store_is_idempotent(db_path: Path) -> None:
    settings_store.initialize_store()
    settings_store.initialize_store()  # must not raise or duplicate schema

    assert db_path.exists()
    with sqlite3.connect(db_path) as conn:
        tables = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='connections'"
        ).fetchall()
        indexes = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index' "
            "AND name='idx_connections_active'"
        ).fetchall()

    assert len(tables) == 1
    assert len(indexes) == 1


def test_round_trip_save_then_load_returns_equivalent_connection(
    db_path: Path,
) -> None:
    original = _make_connection(token_scope="https://other.energy.azure.com/.default")

    settings_store.save_connection("default", original)
    loaded = settings_store.load_connection("default")

    assert loaded is not None
    assert loaded.endpoint == original.endpoint
    assert loaded.tenant_id == original.tenant_id
    assert loaded.client_id == original.client_id
    assert loaded.data_partition_id == original.data_partition_id
    assert loaded.token_scope == original.token_scope
    assert loaded.auth_method == original.auth_method


def test_save_connection_keeps_client_secret_out_of_sqlite(
    db_path: Path,
) -> None:
    """client_secret must NEVER land in the SQLite file; it lives in the OS keyring."""
    sp_with_secret = _make_connection(
        auth_method=AuthMethod.SERVICE_PRINCIPAL,
        client_secret="super-secret-value",
    )

    settings_store.save_connection("sp", sp_with_secret)
    loaded = settings_store.load_connection("sp")

    assert loaded is not None
    # Secret is round-tripped via the (fake) keyring fixture.
    assert loaded.client_secret == "super-secret-value"
    # Defense in depth: confirm the raw bytes never landed in the DB file.
    assert b"super-secret-value" not in db_path.read_bytes()


def test_load_unknown_name_returns_none(db_path: Path) -> None:
    settings_store.initialize_store()

    assert settings_store.load_connection("does-not-exist") is None


def test_load_empty_name_returns_none(db_path: Path) -> None:
    assert settings_store.load_connection("") is None


def test_list_connections_returns_pairs_ordered_by_name(db_path: Path) -> None:
    settings_store.save_connection("zeta", _make_connection())
    settings_store.save_connection("alpha", _make_connection())
    settings_store.save_connection("mike", _make_connection())

    pairs = settings_store.list_connections()

    assert [name for name, _ in pairs] == ["alpha", "mike", "zeta"]
    for _, conn in pairs:
        assert isinstance(conn, ADMEConnection)
        # No keyring entry was ever written for these user-impersonation
        # connections, so client_secret hydrates as the empty string.
        assert conn.client_secret == ""


def test_set_active_connection_enforces_single_active_invariant(
    db_path: Path,
) -> None:
    settings_store.save_connection("a", _make_connection())
    settings_store.save_connection("b", _make_connection())

    settings_store.set_active_connection("a")
    assert settings_store.get_active_connection_name() == "a"

    # Activating B must atomically deactivate A — partial unique index
    # would otherwise raise.
    settings_store.set_active_connection("b")
    assert settings_store.get_active_connection_name() == "b"

    with sqlite3.connect(db_path) as conn:
        active_count = conn.execute(
            "SELECT COUNT(*) FROM connections WHERE is_active = 1"
        ).fetchone()[0]
    assert active_count == 1


def test_set_active_connection_rejects_unknown_name(db_path: Path) -> None:
    settings_store.initialize_store()

    with pytest.raises(SettingsStoreError):
        settings_store.set_active_connection("ghost")


def test_set_active_connection_rejects_empty_name(db_path: Path) -> None:
    settings_store.initialize_store()

    with pytest.raises(SettingsStoreError):
        settings_store.set_active_connection("")


def test_get_active_connection_name_returns_none_on_empty_db(
    db_path: Path,
) -> None:
    settings_store.initialize_store()

    assert settings_store.get_active_connection_name() is None


def test_clear_active_connection_clears_flag(db_path: Path) -> None:
    settings_store.save_connection("a", _make_connection())
    settings_store.set_active_connection("a")

    settings_store.clear_active_connection()

    assert settings_store.get_active_connection_name() is None
    # Row itself must still exist — clearing active is not deletion.
    assert settings_store.load_connection("a") is not None


def test_delete_connection_removes_row(db_path: Path) -> None:
    settings_store.save_connection("a", _make_connection())

    settings_store.delete_connection("a")

    assert settings_store.load_connection("a") is None
    assert settings_store.list_connections() == []


def test_delete_active_connection_clears_active_pointer(db_path: Path) -> None:
    settings_store.save_connection("a", _make_connection())
    settings_store.set_active_connection("a")
    assert settings_store.get_active_connection_name() == "a"

    settings_store.delete_connection("a")

    assert settings_store.get_active_connection_name() is None


def test_delete_missing_connection_is_a_noop(db_path: Path) -> None:
    settings_store.initialize_store()

    # Must not raise even though the row doesn't exist.
    settings_store.delete_connection("never-existed")
    settings_store.delete_connection("")


def test_save_connection_rejects_empty_name(db_path: Path) -> None:
    with pytest.raises(SettingsStoreError):
        settings_store.save_connection("", _make_connection())


def test_save_connection_upserts_existing_row(db_path: Path) -> None:
    original = _make_connection(endpoint="https://old.energy.azure.com")
    updated = _make_connection(endpoint="https://new.energy.azure.com")

    settings_store.save_connection("default", original)
    settings_store.save_connection("default", updated)

    loaded = settings_store.load_connection("default")
    assert loaded is not None
    assert loaded.endpoint == "https://new.energy.azure.com"
    # Only one row should exist after upsert.
    assert len(settings_store.list_connections()) == 1


def test_resaving_active_connection_preserves_active_flag(db_path: Path) -> None:
    settings_store.save_connection("default", _make_connection())
    settings_store.set_active_connection("default")

    settings_store.save_connection(
        "default", _make_connection(endpoint="https://changed.energy.azure.com")
    )

    assert settings_store.get_active_connection_name() == "default"


def test_service_principal_auth_method_round_trips(db_path: Path) -> None:
    sp = _make_connection(
        auth_method=AuthMethod.SERVICE_PRINCIPAL,
        client_secret="vault-resident",
    )

    settings_store.save_connection("sp", sp)
    loaded = settings_store.load_connection("sp")

    assert loaded is not None
    assert loaded.auth_method == AuthMethod.SERVICE_PRINCIPAL
    # client_secret round-trips via the OS keyring (faked in tests).
    assert loaded.client_secret == "vault-resident"
