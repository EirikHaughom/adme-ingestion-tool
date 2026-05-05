"""Tests for ADME health probe helpers."""

from __future__ import annotations

from types import SimpleNamespace
from typing import cast

import pytest
import requests  # type: ignore[import-untyped]

from app.models.connection import OSDU_SERVICES, ADMEConnection
from app.services import health as health_module


def test_check_all_probes_every_service_in_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict[str, object]] = []

    def fake_request(method: str, url: str, **kwargs: object) -> SimpleNamespace:
        calls.append({"method": method, "url": url, **kwargs})
        if "notification" in url:
            return SimpleNamespace(ok=False, status_code=503, text="Unavailable")
        return SimpleNamespace(ok=True, status_code=200, text="")

    monkeypatch.setattr(health_module.requests, "request", fake_request)

    connection = ADMEConnection(
        endpoint="https://example.energy.azure.com/",
        tenant_id="11111111-1111-1111-1111-111111111111",
        client_id="22222222-2222-2222-2222-222222222222",
        data_partition_id="example-opendes",
    )

    results = health_module.check_all(connection, token="test-token")

    assert [result.service_name for result in results] == [
        service_name for service_name, _, _ in OSDU_SERVICES
    ]
    assert results[-1].service_name == "EDS"
    assert results[-2].status == "unhealthy"
    assert any(
        cast(str, call["url"]).endswith("/api/indexer/v2/readiness_check")
        for call in calls
    )
    assert not any(
        cast(str, call["url"]).endswith("/api/indexer/v2/reindex")
        for call in calls
    )
    assert all(
        cast(dict[str, str], call["headers"])["data-partition-id"]
        == "example-opendes"
        for call in calls
    )
    assert all(
        cast(dict[str, str], call["headers"])["Authorization"]
        == "Bearer test-token"
        for call in calls
    )


def test_check_all_marks_request_failures_as_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_request(method: str, url: str, **kwargs: object) -> SimpleNamespace:
        if "schema-service" in url:
            raise requests.RequestException("Network down")
        return SimpleNamespace(ok=True, status_code=200, text="")

    monkeypatch.setattr(health_module.requests, "request", fake_request)

    connection = ADMEConnection(
        endpoint="https://example.energy.azure.com",
        tenant_id="11111111-1111-1111-1111-111111111111",
        client_id="22222222-2222-2222-2222-222222222222",
        data_partition_id="example-opendes",
    )

    results = health_module.check_all(connection, token="test-token")
    schema_result = next(
        result for result in results if result.service_name == "Schema"
    )
    assert schema_result.status == "error"
    assert schema_result.error_message == "Network down"
