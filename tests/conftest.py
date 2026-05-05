"""Shared pytest fixtures for ADME control plane tests."""

from __future__ import annotations

import pytest

from app.models.connection import OSDU_SERVICES, ServiceHealthResult
from tests.support.streamlit_recorder import StreamlitRecorder


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
