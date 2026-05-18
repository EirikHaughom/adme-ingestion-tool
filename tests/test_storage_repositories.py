"""Tests for storage repositories and domain mappings."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import replace
from pathlib import Path

import pytest
from sqlalchemy import inspect
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.orm import Session, sessionmaker

from app.models.connection import ADMEConnection, AuthMethod, ServiceHealthResult
from app.storage.config import StorageConfig, resolve_storage_config
from app.storage.engine import create_engine_from_config
from app.storage.migrations import ensure_storage_ready
from app.storage.repositories.connection_profiles import (
    ConnectionProfile,
    ConnectionProfileRepository,
)
from app.storage.repositories.health_runs import HealthRunRepository
from app.storage.session import create_session_factory


@pytest.fixture
def storage_context(
    tmp_path: Path,
) -> Iterator[
    tuple[StorageConfig, Engine, sessionmaker[Session]]
]:
    db_path = tmp_path / "storage.db"
    config = resolve_storage_config(database_url=f"sqlite:///{db_path.as_posix()}")
    ensure_storage_ready(config)
    engine = create_engine_from_config(config)
    session_factory = create_session_factory(engine)
    try:
        yield config, engine, session_factory
    finally:
        engine.dispose()


def _database_file_bytes(config: StorageConfig) -> bytes:
    database = make_url(config.url).database
    assert database is not None
    database_path = Path(database)
    payload = b""
    for path in database_path.parent.glob(f"{database_path.name}*"):
        if path.is_file():
            payload += path.read_bytes()
    return payload


def test_sqlite_migration_creates_expected_tables_and_omits_secret_column(
    storage_context: tuple[StorageConfig, Engine, sessionmaker[Session]],
) -> None:
    _config, engine, _session_factory = storage_context

    inspector = inspect(engine)

    assert set(inspector.get_table_names()) >= {
        "connection_profiles",
        "active_profile",
        "health_runs",
        "health_run_results",
        "alembic_version",
    }
    profile_columns = {
        column["name"] for column in inspector.get_columns("connection_profiles")
    }
    assert "client_secret" not in profile_columns


def test_connection_profile_round_trip_and_active_pointer(
    storage_context: tuple[StorageConfig, Engine, sessionmaker[Session]],
) -> None:
    _config, _engine, session_factory = storage_context
    repository = ConnectionProfileRepository(session_factory)

    saved = repository.save_profile(
        ConnectionProfile.from_connection(
            display_name="Example ADME",
            connection=_connection(),
        )
    )

    assert saved.id
    assert saved.connection.client_secret == ""
    assert repository.get_profile(saved.id) == saved
    assert repository.list_profiles() == [saved]
    assert repository.get_active_profile() is None

    assert repository.set_active_profile(saved.id) == saved
    assert repository.get_active_profile() == saved

    updated = repository.save_profile(
        replace(saved, display_name="Renamed ADME")
    )
    assert updated.id == saved.id
    assert updated.display_name == "Renamed ADME"
    assert repository.get_active_profile() == updated

    assert repository.delete_profile(saved.id)
    assert repository.get_profile(saved.id) is None
    assert repository.get_active_profile() is None
    assert repository.list_profiles() == []


def test_connection_profile_repository_rejects_client_secret(
    storage_context: tuple[StorageConfig, Engine, sessionmaker[Session]],
) -> None:
    config, _engine, session_factory = storage_context
    repository = ConnectionProfileRepository(session_factory)
    client_secret = "super-secret-repository-value"
    secret_connection = _connection(
        auth_method=AuthMethod.SERVICE_PRINCIPAL,
        client_secret=client_secret,
    )

    with pytest.raises(ValueError, match="client_secret"):
        repository.save_profile(
            ConnectionProfile.from_connection(
                display_name="Secret-bearing profile",
                connection=secret_connection,
            )
        )

    assert repository.list_profiles() == []
    assert client_secret.encode() not in _database_file_bytes(config)


def test_health_run_recording_and_latest_lookup(
    storage_context: tuple[StorageConfig, Engine, sessionmaker[Session]],
) -> None:
    _config, _engine, session_factory = storage_context
    profile_repository = ConnectionProfileRepository(session_factory)
    health_repository = HealthRunRepository(session_factory)
    profile = profile_repository.save_profile(
        ConnectionProfile.from_connection(
            display_name="Example ADME",
            connection=_connection(),
        )
    )
    results = [
        ServiceHealthResult(
            service_name="Storage",
            path="/api/storage/v2/query/kinds?limit=1",
            status="healthy",
            status_code=200,
            response_time_ms=12.5,
        ),
        ServiceHealthResult(
            service_name="Entitlements",
            path="/api/entitlements/v2/groups",
            status="unhealthy",
            status_code=403,
            response_time_ms=20.0,
            error_message="Missing membership.",
        ),
        ServiceHealthResult(
            service_name="Workflow",
            path="/api/workflow/v1/workflow",
            status="error",
            response_time_ms=5000.0,
            error_message="Timed out.",
        ),
    ]

    summary = health_repository.record_run(profile.id, results)
    latest = health_repository.get_latest_for_profile(profile.id)

    assert latest == summary
    assert summary.overall_state == "error"
    assert summary.healthy_count == 1
    assert summary.unhealthy_count == 1
    assert summary.error_count == 1
    assert [result.service_name for result in summary.results] == [
        "Storage",
        "Entitlements",
        "Workflow",
    ]
    assert summary.results[0].response_time_ms == 12.5


def test_health_run_requires_existing_profile(
    storage_context: tuple[StorageConfig, Engine, sessionmaker[Session]],
) -> None:
    _config, _engine, session_factory = storage_context
    repository = HealthRunRepository(session_factory)

    with pytest.raises(ValueError, match="existing profile"):
        repository.record_run("missing-profile", [])


def _connection(
    *,
    auth_method: AuthMethod = AuthMethod.USER_IMPERSONATION,
    client_secret: str = "",
) -> ADMEConnection:
    return ADMEConnection(
        endpoint="https://example.energy.azure.com",
        tenant_id="11111111-1111-1111-1111-111111111111",
        client_id="22222222-2222-2222-2222-222222222222",
        data_partition_id="example-opendes",
        token_scope=" https://energy.azure.com/.default ",
        auth_method=auth_method,
        client_secret=client_secret,
    )
