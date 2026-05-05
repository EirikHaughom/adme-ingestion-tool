"""Tests for ADME OSDU health checks."""

from __future__ import annotations

from dataclasses import dataclass
from typing import cast

import pytest
import requests  # type: ignore[import-untyped]

from app.models.connection import OSDU_SERVICES, ADMEConnection
from app.services.health import SEARCH_PROBE_BODY, check_all


@dataclass
class _FakeResponse:
    status_code: int
    body: str = ""
    reason: str = ""
    json_payload: object | None = None

    @property
    def text(self) -> str:
        return self.body

    def json(self) -> object:
        if self.json_payload is None:
            raise ValueError("No JSON payload")
        return self.json_payload


def test_check_all_probes_every_service_in_contract_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict[str, object]] = []

    def fake_request(**kwargs: object) -> _FakeResponse:
        calls.append(dict(kwargs))
        return _FakeResponse(status_code=200)

    monkeypatch.setattr("app.services.health.requests.request", fake_request)

    results = check_all(_connection(), "access-token")

    assert [result.service_name for result in results] == [
        service_name for service_name, *_ in OSDU_SERVICES
    ]
    assert len(calls) == len(OSDU_SERVICES)
    assert all(result.status == "healthy" for result in results)
    assert all(result.status_code == 200 for result in results)
    assert any(result.service_name == "EDS" for result in results)

    calls_by_url = {cast(str, call["url"]): call for call in calls}
    assert (
        "https://example.energy.azure.com/api/indexer/v2/readiness_check"
        in calls_by_url
    )

    for _, path, method in OSDU_SERVICES:
        call = calls_by_url[f"https://example.energy.azure.com{path}"]
        assert call["method"] == method
        assert call["url"] == f"https://example.energy.azure.com{path}"
        assert call["headers"] == {
            "Authorization": "Bearer access-token",
            "data-partition-id": "example-opendes",
        }
        assert call["timeout"] == 5
        assert call["allow_redirects"] is False
        if path == "/api/search/v2/query":
            assert call["json"] == SEARCH_PROBE_BODY
        else:
            assert call["json"] is None


def test_check_all_marks_http_failures_unhealthy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_request(**kwargs: object) -> _FakeResponse:
        url = cast(str, kwargs["url"])
        if url.endswith("/api/legal/v1/legaltags?valid=true"):
            return _FakeResponse(
                status_code=403,
                body="Forbidden by policy",
                reason="Forbidden",
            )
        return _FakeResponse(status_code=200)

    monkeypatch.setattr("app.services.health.requests.request", fake_request)

    results = check_all(_connection(), "access-token")
    legal_result = next(result for result in results if result.service_name == "Legal")

    assert legal_result.status == "unhealthy"
    assert legal_result.status_code == 403
    assert legal_result.error_message == "Forbidden by policy"
    assert legal_result.response_time_ms is not None


def test_check_all_marks_timeouts_as_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_request(**kwargs: object) -> _FakeResponse:
        url = cast(str, kwargs["url"])
        if url.endswith("/api/workflow/v1/workflow"):
            raise requests.Timeout("workflow timed out")
        return _FakeResponse(status_code=200)

    monkeypatch.setattr("app.services.health.requests.request", fake_request)

    results = check_all(_connection(), "access-token")
    workflow_result = next(
        result for result in results if result.service_name == "Workflow"
    )

    assert workflow_result.status == "error"
    assert workflow_result.status_code is None
    assert workflow_result.error_message == "Timed out after 5 seconds."
    assert workflow_result.response_time_ms is not None


def test_check_all_marks_connection_errors_as_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_request(**kwargs: object) -> _FakeResponse:
        url = cast(str, kwargs["url"])
        if url.endswith("/api/eds/v1/health/readiness_check"):
            raise requests.ConnectionError("eds unreachable")
        return _FakeResponse(status_code=200)

    monkeypatch.setattr("app.services.health.requests.request", fake_request)

    results = check_all(_connection(), "access-token")
    eds_result = next(result for result in results if result.service_name == "EDS")

    assert eds_result.status == "error"
    assert eds_result.status_code is None
    assert eds_result.error_message == "eds unreachable"
    assert eds_result.response_time_ms is not None


def test_check_all_requires_a_non_empty_token() -> None:
    with pytest.raises(ValueError, match="non-empty bearer token"):
        check_all(_connection(), "   ")


def _connection() -> ADMEConnection:
    return ADMEConnection(
        endpoint="https://example.energy.azure.com/",
        tenant_id="tenant-id",
        client_id="client-id",
        data_partition_id="example-opendes",
    )
