"""Tests for ADME Entitlements smoke-test service calls."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, cast
from urllib.parse import quote

import pytest
import requests  # type: ignore[import-untyped]

from app.models.connection import (
    ADMEConnection,
    AuthMethod,
    EntitlementsCallResult,
)
from app.services import entitlements as entitlements_module
from app.services.entitlements import (
    ENTITLEMENTS_TIMEOUT_SECONDS,
    GROUPS_PATH,
    fetch_groups,
    fetch_my_groups,
)

_OID = "11111111-2222-3333-4444-555555555555"


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


def _connection(
    *,
    endpoint: str = "https://example.energy.azure.com",
    auth_method: AuthMethod = AuthMethod.USER_IMPERSONATION,
    client_secret: str = "",
) -> ADMEConnection:
    return ADMEConnection(
        endpoint=endpoint,
        tenant_id="11111111-1111-1111-1111-111111111111",
        client_id="22222222-2222-2222-2222-222222222222",
        data_partition_id="example-opendes",
        auth_method=auth_method,
        client_secret=client_secret,
    )


def _patch_get(
    monkeypatch: pytest.MonkeyPatch,
    response_factory: Any,
) -> list[dict[str, Any]]:
    captured: list[dict[str, Any]] = []

    def fake_get(**kwargs: Any) -> Any:
        captured.append(kwargs)
        return response_factory(**kwargs)

    monkeypatch.setattr(entitlements_module.requests, "get", fake_get)
    return captured


# ---------------------------------------------------------------------------
# fetch_my_groups — happy path
# ---------------------------------------------------------------------------


def test_fetch_my_groups_happy_path(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = {
        "desId": "operator@example.com",
        "memberEmail": "operator@example.com",
        "groups": [
            {"name": "users", "email": "users@example", "description": "all"},
            {"name": "admins", "email": "admins@example", "description": "ops"},
        ],
    }
    captured = _patch_get(
        monkeypatch,
        lambda **_: _FakeResponse(
            status_code=200,
            headers={"correlation-id": "corr-mygroups-1"},
            json_payload=payload,
        ),
    )

    result = fetch_my_groups(_connection(), token="user-token", object_id=_OID)

    assert isinstance(result, EntitlementsCallResult)
    assert result.ok is True
    assert result.http_status == 200
    assert result.data == payload
    assert result.raw_response == payload
    # Endpoint label mirrors the per-OID path. The Streamlit page collapses
    # this for the chart legend; the raw label is preserved here for
    # diagnostics in the history table.
    assert result.endpoint == f"members.{_OID}.groups"
    assert _OID in result.path
    assert result.path.endswith("/groups?type=none")
    assert result.correlation_id == "corr-mygroups-1"
    assert result.latency_ms >= 0.0
    assert len(captured) == 1
    expected_url = (
        "https://example.energy.azure.com/api/entitlements/v2/members/"
        f"{_OID}/groups?type=none"
    )
    assert captured[0]["url"] == expected_url


# ---------------------------------------------------------------------------
# fetch_my_groups — URL building (quoting)
# ---------------------------------------------------------------------------


def test_fetch_my_groups_url_contains_quoted_oid_and_type_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Standard GUID OIDs round-trip unchanged through urllib quoting."""
    captured = _patch_get(
        monkeypatch,
        lambda **_: _FakeResponse(status_code=200, json_payload={"groups": []}),
    )

    fetch_my_groups(_connection(), token="user-token", object_id=_OID)

    quoted = quote(_OID, safe="")
    assert quoted == _OID  # GUIDs (hex + dashes) are unreserved
    assert captured[0]["url"] == (
        "https://example.energy.azure.com/api/entitlements/v2/members/"
        f"{quoted}/groups?type=none"
    )


def test_fetch_my_groups_quotes_special_characters_in_oid(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Non-GUID OIDs containing ``+`` and other reserved chars are escaped."""
    captured = _patch_get(
        monkeypatch,
        lambda **_: _FakeResponse(status_code=200, json_payload={"groups": []}),
    )
    weird_oid = "a+b/c d"

    fetch_my_groups(_connection(), token="user-token", object_id=weird_oid)

    quoted = quote(weird_oid, safe="")
    assert quoted == "a%2Bb%2Fc%20d"
    assert captured[0]["url"] == (
        "https://example.energy.azure.com/api/entitlements/v2/members/"
        f"{quoted}/groups?type=none"
    )


def test_fetch_my_groups_url_strips_trailing_slash_on_endpoint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured = _patch_get(
        monkeypatch,
        lambda **_: _FakeResponse(status_code=200, json_payload={"groups": []}),
    )

    fetch_my_groups(
        _connection(endpoint="https://example.energy.azure.com/"),
        token="user-token",
        object_id=_OID,
    )

    assert captured[0]["url"] == (
        "https://example.energy.azure.com/api/entitlements/v2/members/"
        f"{_OID}/groups?type=none"
    )


# ---------------------------------------------------------------------------
# fetch_my_groups — outgoing headers
# ---------------------------------------------------------------------------


def test_fetch_my_groups_outgoing_request_carries_required_headers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured = _patch_get(
        monkeypatch,
        lambda **_: _FakeResponse(
            status_code=200,
            json_payload={"desId": "x", "memberEmail": "y", "groups": []},
        ),
    )

    fetch_my_groups(_connection(), token="bearer-abc", object_id=_OID)

    assert len(captured) == 1
    headers = captured[0]["headers"]
    assert headers["Authorization"] == "Bearer bearer-abc"
    assert headers["data-partition-id"] == "example-opendes"
    assert headers["Accept"] == "application/json"
    assert captured[0]["timeout"] == ENTITLEMENTS_TIMEOUT_SECONDS
    assert captured[0]["allow_redirects"] is False


# ---------------------------------------------------------------------------
# fetch_my_groups — HTTP error responses
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("status_code", [401, 403, 500])
def test_fetch_my_groups_returns_failure_on_http_error(
    monkeypatch: pytest.MonkeyPatch, status_code: int
) -> None:
    _patch_get(
        monkeypatch,
        lambda **_: _FakeResponse(
            status_code=status_code,
            headers={"correlation-id": f"corr-{status_code}"},
            json_payload={"message": f"boom {status_code}"},
        ),
    )

    result = fetch_my_groups(_connection(), token="user-token", object_id=_OID)

    assert result.ok is False
    assert result.http_status == status_code
    assert result.error_message
    assert f"boom {status_code}" in result.error_message
    assert result.correlation_id == f"corr-{status_code}"
    assert result.data is None
    assert result.raw_response == {"message": f"boom {status_code}"}


# ---------------------------------------------------------------------------
# fetch_my_groups — transport failures
# ---------------------------------------------------------------------------


def test_fetch_my_groups_handles_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_get(**_: Any) -> Any:
        raise requests.exceptions.Timeout("read timed out")

    monkeypatch.setattr(entitlements_module.requests, "get", fake_get)

    result = fetch_my_groups(_connection(), token="user-token", object_id=_OID)

    assert result.ok is False
    assert result.http_status is None
    assert result.error_message is not None
    assert "timed out" in result.error_message.lower()
    assert str(ENTITLEMENTS_TIMEOUT_SECONDS) in result.error_message
    assert result.correlation_id is None
    assert result.raw_response is None
    assert result.data is None
    assert result.latency_ms >= 0.0


def test_fetch_my_groups_handles_connection_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_get(**_: Any) -> Any:
        raise requests.exceptions.ConnectionError("dns failure")

    monkeypatch.setattr(entitlements_module.requests, "get", fake_get)

    result = fetch_my_groups(_connection(), token="user-token", object_id=_OID)

    assert result.ok is False
    assert result.http_status is None
    assert result.error_message is not None
    assert "ConnectionError" in result.error_message
    assert "dns failure" in result.error_message
    assert result.correlation_id is None
    assert result.data is None


# ---------------------------------------------------------------------------
# fetch_my_groups — input validation
# ---------------------------------------------------------------------------


def test_fetch_my_groups_rejects_invalid_connection() -> None:
    bad = ADMEConnection(
        endpoint="",
        tenant_id="",
        client_id="",
        data_partition_id="",
    )

    with pytest.raises(ValueError, match="ADME connection is incomplete"):
        fetch_my_groups(bad, token="user-token", object_id=_OID)


@pytest.mark.parametrize("token", ["", "   ", "\t\n"])
def test_fetch_my_groups_rejects_empty_token(token: str) -> None:
    with pytest.raises(ValueError, match="non-empty bearer token"):
        fetch_my_groups(_connection(), token=token, object_id=_OID)


@pytest.mark.parametrize("oid", ["", "   ", "\t\n"])
def test_fetch_my_groups_rejects_empty_object_id(oid: str) -> None:
    with pytest.raises(ValueError, match="Entra Object ID"):
        fetch_my_groups(_connection(), token="user-token", object_id=oid)


# ---------------------------------------------------------------------------
# fetch_groups — happy path (unchanged contract)
# ---------------------------------------------------------------------------


def test_fetch_groups_happy_path(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = {
        "groups": [
            {"name": "users", "email": "users@example", "description": "all"},
            {"name": "admins", "email": "admins@example", "description": "ops"},
            {"name": "viewers", "email": "viewers@example", "description": ""},
        ]
    }
    _patch_get(
        monkeypatch,
        lambda **_: _FakeResponse(
            status_code=200,
            headers={"x-correlation-id": "corr-groups-1"},
            json_payload=payload,
        ),
    )

    result = fetch_groups(_connection(), token="user-token")

    assert result.ok is True
    assert result.http_status == 200
    assert result.endpoint == "groups"
    assert result.path == GROUPS_PATH
    groups = cast(dict[str, Any], result.data)["groups"]
    assert isinstance(groups, list)
    assert len(groups) == 3
    assert result.correlation_id == "corr-groups-1"
    assert result.latency_ms >= 0.0


# ---------------------------------------------------------------------------
# fetch_groups — HTTP error responses
# ---------------------------------------------------------------------------


def test_fetch_groups_failure_with_text_body_falls_back_to_text(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_get(
        monkeypatch,
        lambda **_: _FakeResponse(
            status_code=502,
            headers={"x-request-id": "corr-text"},
            body="Bad gateway",
            raise_on_json=True,
        ),
    )

    result = fetch_groups(_connection(), token="user-token")

    assert result.ok is False
    assert result.http_status == 502
    assert result.error_message == "Bad gateway"
    assert result.raw_response == "Bad gateway"
    assert result.correlation_id == "corr-text"
    assert result.data is None


def test_fetch_groups_failure_without_correlation_header_returns_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_get(
        monkeypatch,
        lambda **_: _FakeResponse(
            status_code=403,
            json_payload={"message": "denied"},
        ),
    )

    result = fetch_groups(_connection(), token="user-token")

    assert result.ok is False
    assert result.correlation_id is None


def test_fetch_groups_handles_connection_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_get(**_: Any) -> Any:
        raise requests.exceptions.ConnectionError("dns failure")

    monkeypatch.setattr(entitlements_module.requests, "get", fake_get)

    result = fetch_groups(_connection(), token="user-token")

    assert result.ok is False
    assert result.http_status is None
    assert result.error_message is not None
    assert "ConnectionError" in result.error_message
    assert "dns failure" in result.error_message
    assert result.correlation_id is None
    assert result.data is None


# ---------------------------------------------------------------------------
# Correlation ID extraction (covers shared _call_entitlements machinery)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "header_name",
    ["correlation-id", "X-Correlation-ID", "Request-Id", "X-Request-Id"],
)
def test_correlation_id_lookup_is_case_insensitive(
    monkeypatch: pytest.MonkeyPatch, header_name: str
) -> None:
    _patch_get(
        monkeypatch,
        lambda **_: _FakeResponse(
            status_code=200,
            headers={header_name: "corr-from-" + header_name},
            json_payload={"groups": []},
        ),
    )

    result = fetch_groups(_connection(), token="user-token")

    assert result.ok is True
    assert result.correlation_id == "corr-from-" + header_name


def test_correlation_id_first_hit_wins(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_get(
        monkeypatch,
        lambda **_: _FakeResponse(
            status_code=200,
            headers={
                "correlation-id": "winner",
                "x-correlation-id": "second",
                "request-id": "third",
                "x-request-id": "fourth",
            },
            json_payload={"groups": []},
        ),
    )

    result = fetch_groups(_connection(), token="user-token")

    assert result.correlation_id == "winner"


def test_correlation_id_falls_back_to_later_candidates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_get(
        monkeypatch,
        lambda **_: _FakeResponse(
            status_code=200,
            headers={"X-Request-Id": "only-this"},
            json_payload={"groups": []},
        ),
    )

    result = fetch_groups(_connection(), token="user-token")

    assert result.correlation_id == "only-this"


# ---------------------------------------------------------------------------
# fetch_groups — URL building & headers (unchanged contract)
# ---------------------------------------------------------------------------


def test_fetch_groups_url_strips_trailing_slash_on_endpoint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured = _patch_get(
        monkeypatch,
        lambda **_: _FakeResponse(status_code=200, json_payload={"groups": []}),
    )

    fetch_groups(
        _connection(endpoint="https://example.energy.azure.com/"),
        token="user-token",
    )

    assert (
        captured[0]["url"]
        == "https://example.energy.azure.com/api/entitlements/v2/groups"
    )


def test_fetch_groups_outgoing_request_carries_required_headers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured = _patch_get(
        monkeypatch,
        lambda **_: _FakeResponse(
            status_code=200, json_payload={"groups": []}
        ),
    )

    fetch_groups(_connection(), token="bearer-abc")

    assert len(captured) == 1
    headers = captured[0]["headers"]
    assert headers["Authorization"] == "Bearer bearer-abc"
    assert headers["data-partition-id"] == "example-opendes"
    assert headers["Accept"] == "application/json"
    assert captured[0]["timeout"] == ENTITLEMENTS_TIMEOUT_SECONDS
    assert captured[0]["allow_redirects"] is False


# ---------------------------------------------------------------------------
# fetch_groups — input validation
# ---------------------------------------------------------------------------


def test_fetch_groups_rejects_invalid_service_principal_connection() -> None:
    """Service principal without client_secret must be rejected."""
    bad = _connection(auth_method=AuthMethod.SERVICE_PRINCIPAL, client_secret="")

    with pytest.raises(ValueError, match="ADME connection is incomplete"):
        fetch_groups(bad, token="user-token")


@pytest.mark.parametrize("token", ["", "   "])
def test_fetch_groups_rejects_empty_token(token: str) -> None:
    with pytest.raises(ValueError, match="non-empty bearer token"):
        fetch_groups(_connection(), token=token)
