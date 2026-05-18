"""Shared pytest fixtures for ADME control plane tests."""

from __future__ import annotations

import sys
import types
from pathlib import Path

import pytest

from app.models.connection import OSDU_SERVICES, ServiceHealthResult
from tests.support.streamlit_recorder import StreamlitRecorder


@pytest.fixture(autouse=True)
def _isolate_keyring(monkeypatch: pytest.MonkeyPatch) -> dict[tuple[str, str], str]:
    """Replace the ``keyring`` module with an in-memory fake for ALL tests.

    ``app.services.settings_store`` lazily imports ``keyring`` inside its
    secret helpers.  Without this fixture, any test that calls
    ``save_connection``/``delete_connection`` would touch the real Windows
    Credential Manager (or Linux/macOS equivalent).  We replace the module
    in ``sys.modules`` so the lazy ``import keyring`` resolves to a stub
    whose state is per-test (a fresh dict).  Tests that need to assert on
    keyring calls install their own fake on top of this one.
    """
    store: dict[tuple[str, str], str] = {}

    fake = types.ModuleType("keyring")
    errors = types.ModuleType("keyring.errors")

    class PasswordDeleteError(Exception):
        pass

    errors.PasswordDeleteError = PasswordDeleteError  # type: ignore[attr-defined]

    def set_password(service: str, name: str, secret: str) -> None:
        store[(service, name)] = secret

    def get_password(service: str, name: str) -> str | None:
        return store.get((service, name))

    def delete_password(service: str, name: str) -> None:
        try:
            del store[(service, name)]
        except KeyError as exc:
            raise PasswordDeleteError("no such password") from exc

    fake.set_password = set_password  # type: ignore[attr-defined]
    fake.get_password = get_password  # type: ignore[attr-defined]
    fake.delete_password = delete_password  # type: ignore[attr-defined]

    monkeypatch.setitem(sys.modules, "keyring", fake)
    monkeypatch.setitem(sys.modules, "keyring.errors", errors)
    return store


@pytest.fixture(autouse=True)
def _isolate_settings_db(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Path:
    """Point the settings store at a per-test SQLite path.

    Without this fixture, ``app.connection_state.ensure_session_defaults``
    hydrates from the operator's real ``~/.adme-ingestion-tool/settings.db``
    during any test that doesn't explicitly set ``ADME_SETTINGS_DB``.  That
    cross-contaminates tests which assume a clean "no configuration yet"
    starting state (notably the main page and Settings page tests).  By
    making isolation autouse, hydration NEVER touches the user's real
    profile during testing.
    """
    target = tmp_path / "settings.db"
    monkeypatch.setenv("ADME_SETTINGS_DB", str(target))
    return target


@pytest.fixture(autouse=True)
def _isolate_run_history_db(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Path:
    """Point the run-history store at a per-test SQLite path.

    Mirrors ``_isolate_settings_db``: without this fixture, any test that
    touches the Manifest / File / History pages or the run_history
    service directly would write to the operator's real
    ``~/.adme-ingestion-tool/run-history.db``. Autouse keeps tests off
    the user's profile by default.
    """
    target = tmp_path / "run-history.db"
    monkeypatch.setenv("ADME_RUN_HISTORY_DB", str(target))
    return target


@pytest.fixture
def run_history_tmp_db(_isolate_run_history_db: Path) -> Path:
    """Return the per-test run-history DB path.

    Thin wrapper around the autouse isolator so tests that want the
    path explicitly (for assertions on db_info, etc.) can request it.
    """
    return _isolate_run_history_db


@pytest.fixture(autouse=True)
def _isolate_storage_database(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Route default persistent storage to a per-test SQLite database."""
    database_path = tmp_path / "adme-test.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{database_path.as_posix()}")


@pytest.fixture
def app_title() -> str:
    """Return the expected application title."""
    return "ADME Control Plane"


@pytest.fixture
def streamlit_recorder() -> StreamlitRecorder:
    """Provide a Streamlit call recorder for page-level tests."""
    return StreamlitRecorder()


@pytest.fixture
def adme_core_services() -> tuple[str, ...]:
    """Return the core ADME/OSDU services expected in health validation."""
    return tuple(service_name.lower() for service_name, *_ in OSDU_SERVICES)


@pytest.fixture
def user_impersonation_connection_payload() -> dict[str, str]:
    """Return a representative user-impersonation connection payload."""
    return {
        "auth_method": "user_impersonation",
        "tenant_id": "11111111-1111-1111-1111-111111111111",
        "client_id": "22222222-2222-2222-2222-222222222222",
        "endpoint": "https://example.energy.azure.com",
        "data_partition_id": "example-opendes",
    }


@pytest.fixture
def service_principal_connection_payload() -> dict[str, str]:
    """Return a representative service-principal connection payload."""
    return {
        "auth_method": "service_principal",
        "tenant_id": "11111111-1111-1111-1111-111111111111",
        "client_id": "22222222-2222-2222-2222-222222222222",
        "endpoint": "https://example.energy.azure.com",
        "data_partition_id": "example-opendes",
        "client_secret": "test-client-secret",
    }


@pytest.fixture
def healthy_service_report(
    adme_core_services: tuple[str, ...],
) -> dict[str, dict[str, str | int | None]]:
    """Return a fully healthy service-by-service status report."""
    return {
        service: {"state": "healthy", "status_code": 200, "detail": None}
        for service in adme_core_services
    }


@pytest.fixture
def healthy_service_results() -> list[ServiceHealthResult]:
    """Return healthy results for every configured OSDU service."""
    return [
        ServiceHealthResult(
            service_name=service_name,
            path=path,
            status="healthy",
            status_code=200,
            response_time_ms=42.5,
        )
        for service_name, path, _ in OSDU_SERVICES
    ]


@pytest.fixture
def degraded_service_results(
    healthy_service_results: list[ServiceHealthResult],
) -> list[ServiceHealthResult]:
    """Return a mixed result set with unhealthy and error services."""
    results = [result for result in healthy_service_results]
    results[4] = ServiceHealthResult(
        service_name=results[4].service_name,
        path=results[4].path,
        status="unhealthy",
        status_code=403,
        response_time_ms=18.0,
        error_message="Missing entitlements membership.",
    )
    results[5] = ServiceHealthResult(
        service_name=results[5].service_name,
        path=results[5].path,
        status="error",
        response_time_ms=5000.0,
        error_message="Timed out waiting for workflow service.",
    )
    return results


@pytest.fixture
def degraded_service_report(
    healthy_service_report: dict[str, dict[str, str | int | None]],
) -> dict[str, dict[str, str | int | None]]:
    """Return a mixed health report with representative failures."""
    report = {
        service: status.copy() for service, status in healthy_service_report.items()
    }
    report["entitlements"] = {
        "state": "unauthorized",
        "status_code": 403,
        "detail": "Missing entitlements membership.",
    }
    report["workflow"] = {
        "state": "unreachable",
        "status_code": 504,
        "detail": "Timed out waiting for health endpoint.",
    }
    return report
