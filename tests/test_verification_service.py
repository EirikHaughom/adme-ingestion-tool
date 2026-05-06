"""Tests for ``app.services.verification.search_records_by_kind``."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pytest
import requests  # type: ignore[import-untyped]

from app.models.connection import ADMEConnection, AuthMethod
from app.models.osdu import SearchResult
from app.services import verification as verification_module
from app.services.verification import (
    DEFAULT_SEARCH_LIMIT,
    SEARCH_QUERY_PATH,
    VERIFICATION_TIMEOUT_SECONDS,
    search_records_by_kind,
)


@dataclass
class _FakeResponse:
    status_code: int
    headers: dict[str, str] = field(default_factory=dict)
    json_payload: object | None = None
    body: str = ""
    raise_on_json: bool = False

    @property
    def text(self) -> str:
        return self.body

    def json(self) -> object:
        if self.raise_on_json or self.json_payload is None:
            raise ValueError("No JSON payload")
        return self.json_payload


def _connection() -> ADMEConnection:
    return ADMEConnection(
        endpoint="https://example.energy.azure.com",
        tenant_id="11111111-1111-1111-1111-111111111111",
        client_id="22222222-2222-2222-2222-222222222222",
        data_partition_id="example-opendes",
        auth_method=AuthMethod.USER_IMPERSONATION,
    )


def _patch_post(
    monkeypatch: pytest.MonkeyPatch,
    response_factory: Any,
) -> list[dict[str, Any]]:
    captured: list[dict[str, Any]] = []

    def fake_post(**kwargs: Any) -> Any:
        captured.append(kwargs)
        return response_factory(**kwargs)

    monkeypatch.setattr(verification_module.requests, "post", fake_post)
    return captured


_KIND = "osdu:wks:reference-data--AliasNameType:1.0.0"


# ---------------------------------------------------------------------------
# Happy paths
# ---------------------------------------------------------------------------


def test_search_happy_path_with_total_count(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured = _patch_post(
        monkeypatch,
        lambda **_: _FakeResponse(
            status_code=200,
            headers={"correlation-id": "corr-search-1"},
            json_payload={
                "totalCount": 5,
                "results": [{"id": "1"}, {"id": "2"}],
            },
        ),
    )

    result = search_records_by_kind(_connection(), token="t", kind=_KIND)

    assert isinstance(result, SearchResult)
    assert result.ok is True
    assert result.http_status == 200
    assert result.kind == _KIND
    assert result.count == 5  # totalCount wins, not len(results)
    assert len(result.records) == 2
    assert result.correlation_id == "corr-search-1"
    assert result.latency_ms >= 0.0
    assert captured[0]["url"].endswith(SEARCH_QUERY_PATH)
    assert captured[0]["json"] == {
        "kind": _KIND,
        "limit": DEFAULT_SEARCH_LIMIT,
        "offset": 0,
    }


def test_search_happy_path_without_total_count_falls_back_to_len(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_post(
        monkeypatch,
        lambda **_: _FakeResponse(
            status_code=200,
            json_payload={
                "results": [{"id": "1"}, {"id": "2"}, {"id": "3"}],
            },
        ),
    )

    result = search_records_by_kind(_connection(), token="t", kind=_KIND)

    assert result.ok is True
    assert result.count == 3
    assert len(result.records) == 3


def test_search_empty_results_is_ok_with_count_zero(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_post(
        monkeypatch,
        lambda **_: _FakeResponse(
            status_code=200,
            json_payload={"totalCount": 0, "results": []},
        ),
    )

    result = search_records_by_kind(_connection(), token="t", kind=_KIND)

    assert result.ok is True
    assert result.count == 0
    assert result.records == []


def test_search_custom_limit_is_honored(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured = _patch_post(
        monkeypatch,
        lambda **_: _FakeResponse(
            status_code=200, json_payload={"totalCount": 0, "results": []}
        ),
    )

    search_records_by_kind(_connection(), token="t", kind=_KIND, limit=25)

    assert captured[0]["json"] == {"kind": _KIND, "limit": 25, "offset": 0}


# ---------------------------------------------------------------------------
# Outgoing headers + correlation
# ---------------------------------------------------------------------------


def test_search_outgoing_request_carries_required_headers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured = _patch_post(
        monkeypatch,
        lambda **_: _FakeResponse(
            status_code=200, json_payload={"totalCount": 0, "results": []}
        ),
    )

    search_records_by_kind(_connection(), token="bearer-abc", kind=_KIND)

    headers = captured[0]["headers"]
    assert headers["Authorization"] == "Bearer bearer-abc"
    assert headers["data-partition-id"] == "example-opendes"
    assert headers["Accept"] == "application/json"
    assert headers["Content-Type"] == "application/json"
    assert captured[0]["timeout"] == VERIFICATION_TIMEOUT_SECONDS
    assert captured[0]["allow_redirects"] is False


@pytest.mark.parametrize(
    "header_name",
    ["correlation-id", "X-Correlation-ID", "Request-Id", "X-Request-Id"],
)
def test_search_correlation_id_case_insensitive(
    monkeypatch: pytest.MonkeyPatch, header_name: str
) -> None:
    _patch_post(
        monkeypatch,
        lambda **_: _FakeResponse(
            status_code=200,
            headers={header_name: "corr-x"},
            json_payload={"totalCount": 0, "results": []},
        ),
    )

    result = search_records_by_kind(_connection(), token="t", kind=_KIND)

    assert result.correlation_id == "corr-x"


# ---------------------------------------------------------------------------
# HTTP errors
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("status_code", [401, 403, 500])
def test_search_http_errors(
    monkeypatch: pytest.MonkeyPatch, status_code: int
) -> None:
    _patch_post(
        monkeypatch,
        lambda **_: _FakeResponse(
            status_code=status_code,
            headers={"correlation-id": f"corr-{status_code}"},
            json_payload={"message": f"boom {status_code}"},
        ),
    )

    result = search_records_by_kind(_connection(), token="t", kind=_KIND)

    assert result.ok is False
    assert result.http_status == status_code
    assert result.count == 0
    assert result.records == []
    assert result.error_message is not None
    assert f"boom {status_code}" in result.error_message
    assert result.correlation_id == f"corr-{status_code}"


# ---------------------------------------------------------------------------
# Transport failures
# ---------------------------------------------------------------------------


def test_search_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_post(**_: Any) -> Any:
        raise requests.exceptions.Timeout("slow")

    monkeypatch.setattr(verification_module.requests, "post", fake_post)

    result = search_records_by_kind(_connection(), token="t", kind=_KIND)

    assert result.ok is False
    assert result.http_status is None
    assert "timed out" in (result.error_message or "").lower()
    assert str(VERIFICATION_TIMEOUT_SECONDS) in (result.error_message or "")
    assert result.count == 0


def test_search_connection_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_post(**_: Any) -> Any:
        raise requests.exceptions.ConnectionError("dns failure")

    monkeypatch.setattr(verification_module.requests, "post", fake_post)

    result = search_records_by_kind(_connection(), token="t", kind=_KIND)

    assert result.ok is False
    assert result.http_status is None
    assert "ConnectionError" in (result.error_message or "")
    assert result.records == []


# ---------------------------------------------------------------------------
# Pre-flight validation
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("kind", ["", "   ", "\t\n"])
def test_search_rejects_blank_kind(kind: str) -> None:
    with pytest.raises(ValueError, match="kind"):
        search_records_by_kind(_connection(), token="t", kind=kind)


@pytest.mark.parametrize("token", ["", "   "])
def test_search_rejects_blank_token(token: str) -> None:
    with pytest.raises(ValueError, match="non-empty bearer token"):
        search_records_by_kind(_connection(), token=token, kind=_KIND)


def test_search_rejects_invalid_connection() -> None:
    bad = ADMEConnection(
        endpoint="", tenant_id="", client_id="", data_partition_id=""
    )
    with pytest.raises(ValueError, match="ADME connection is incomplete"):
        search_records_by_kind(bad, token="t", kind=_KIND)


@pytest.mark.parametrize("limit", [0, -1, -100])
def test_search_rejects_non_positive_limit(limit: int) -> None:
    with pytest.raises(ValueError, match="limit"):
        search_records_by_kind(_connection(), token="t", kind=_KIND, limit=limit)
