"""Tests for ``app.services.legal_tags``: 6 HTTP functions + identity regression."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from urllib.parse import quote

import pytest
import requests  # type: ignore[import-untyped]

from app.models.connection import ADMEConnection, AuthMethod
from app.models.osdu import (
    LegalTag,
    LegalTagDetailResult,
    LegalTagListResult,
    LegalTagOperationResult,
    LegalTagPropertiesResult,
)
from app.services import ingestion as ingestion_module
from app.services import legal_tags as legal_tags_module
from app.services.legal_tags import (
    LEGAL_TAG_PROPERTIES_PATH,
    LEGAL_TAGS_PATH,
    LEGAL_TAGS_TIMEOUT_SECONDS,
    create_legal_tag,
    delete_legal_tag,
    get_legal_tag,
    get_legal_tag_properties,
    list_legal_tags,
    update_legal_tag,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


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
    data_partition_id: str = "example-opendes",
) -> ADMEConnection:
    return ADMEConnection(
        endpoint=endpoint,
        tenant_id="11111111-1111-1111-1111-111111111111",
        client_id="22222222-2222-2222-2222-222222222222",
        data_partition_id=data_partition_id,
        auth_method=auth_method,
        client_secret=client_secret,
    )


def _patch_method(
    monkeypatch: pytest.MonkeyPatch,
    method: str,
    response_factory: Any,
) -> list[dict[str, Any]]:
    captured: list[dict[str, Any]] = []

    def fake(**kwargs: Any) -> Any:
        captured.append(kwargs)
        return response_factory(**kwargs)

    monkeypatch.setattr(legal_tags_module.requests, method, fake)
    return captured


def _patch_get(
    monkeypatch: pytest.MonkeyPatch, response_factory: Any
) -> list[dict[str, Any]]:
    return _patch_method(monkeypatch, "get", response_factory)


def _patch_post(
    monkeypatch: pytest.MonkeyPatch, response_factory: Any
) -> list[dict[str, Any]]:
    return _patch_method(monkeypatch, "post", response_factory)


def _patch_put(
    monkeypatch: pytest.MonkeyPatch, response_factory: Any
) -> list[dict[str, Any]]:
    return _patch_method(monkeypatch, "put", response_factory)


def _patch_delete(
    monkeypatch: pytest.MonkeyPatch, response_factory: Any
) -> list[dict[str, Any]]:
    return _patch_method(monkeypatch, "delete", response_factory)


# Realistic ADME response shapes (per Darryl's Section A research).
_LEGAL_TAG_DTO: dict[str, Any] = {
    "name": "opendes-public-usa-dataset",
    "description": "Public USA dataset",
    "properties": {
        "countryOfOrigin": ["US"],
        "contractId": "No Contract Related",
        "expirationDate": "2099-12-31",
        "originator": "ADME Operator",
        "dataType": "Public Domain Data",
        "securityClassification": "Public",
        "personalData": "No Personal Data",
        "exportClassification": "EAR99",
    },
    "isValid": True,
}

_VALID_PROPERTIES: dict[str, Any] = {
    "countryOfOrigin": ["US"],
    "contractId": "No Contract Related",
    "expirationDate": "2099-12-31",
    "originator": "ADME Operator",
    "dataType": "Public Domain Data",
    "securityClassification": "Public",
    "personalData": "No Personal Data",
    "exportClassification": "EAR99",
}


# ===========================================================================
# Identity regression — ingestion + legal_tags share LEGAL_TAGS_PATH
# ===========================================================================


def test_legal_tags_path_is_owned_by_legal_tags_module() -> None:
    """``ingestion.LEGAL_TAGS_PATH`` must be the SAME OBJECT as legal_tags's."""
    assert ingestion_module.LEGAL_TAGS_PATH is LEGAL_TAGS_PATH
    assert LEGAL_TAGS_PATH == "/api/legal/v1/legaltags"


# ===========================================================================
# list_legal_tags
# ===========================================================================


def test_list_legal_tags_happy_path(monkeypatch: pytest.MonkeyPatch) -> None:
    captured = _patch_get(
        monkeypatch,
        lambda **_: _FakeResponse(
            status_code=200,
            headers={"correlation-id": "corr-list-1"},
            json_payload={"legalTags": [_LEGAL_TAG_DTO]},
        ),
    )

    result = list_legal_tags(_connection(), token="t")

    assert isinstance(result, LegalTagListResult)
    assert result.ok is True
    assert result.http_status == 200
    assert len(result.items) == 1
    tag = result.items[0]
    assert isinstance(tag, LegalTag)
    assert tag.name == "opendes-public-usa-dataset"
    assert tag.is_valid is True
    assert tag.properties["countryOfOrigin"] == ["US"]
    assert result.correlation_id == "corr-list-1"
    assert result.latency_ms >= 0.0
    assert captured[0]["url"].endswith(LEGAL_TAGS_PATH)


def test_list_legal_tags_valid_true_query_string(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured = _patch_get(
        monkeypatch,
        lambda **_: _FakeResponse(
            status_code=200, json_payload={"legalTags": []}
        ),
    )
    list_legal_tags(_connection(), token="t", valid=True)
    assert captured[0]["url"].endswith(f"{LEGAL_TAGS_PATH}?valid=true")


def test_list_legal_tags_valid_false_query_string(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured = _patch_get(
        monkeypatch,
        lambda **_: _FakeResponse(
            status_code=200, json_payload={"legalTags": []}
        ),
    )
    list_legal_tags(_connection(), token="t", valid=False)
    assert captured[0]["url"].endswith(f"{LEGAL_TAGS_PATH}?valid=false")


def test_list_legal_tags_valid_none_omits_query_string(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured = _patch_get(
        monkeypatch,
        lambda **_: _FakeResponse(
            status_code=200, json_payload={"legalTags": []}
        ),
    )
    list_legal_tags(_connection(), token="t", valid=None)
    assert "?" not in captured[0]["url"]


@pytest.mark.parametrize("status_code", [401, 403, 404, 500])
def test_list_legal_tags_http_errors(
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

    result = list_legal_tags(_connection(), token="t")

    assert result.ok is False
    assert result.http_status == status_code
    assert result.error_message is not None
    assert f"boom {status_code}" in result.error_message
    assert result.correlation_id == f"corr-{status_code}"
    assert result.items == []


def test_list_legal_tags_error_message_falls_back_to_http_when_body_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_get(
        monkeypatch,
        lambda **_: _FakeResponse(
            status_code=500, body="", raise_on_json=True
        ),
    )

    result = list_legal_tags(_connection(), token="t")

    assert result.ok is False
    assert result.error_message == "HTTP 500"


def test_list_legal_tags_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_get(**_: Any) -> Any:
        raise requests.exceptions.Timeout("slow")

    monkeypatch.setattr(legal_tags_module.requests, "get", fake_get)
    result = list_legal_tags(_connection(), token="t")
    assert result.ok is False
    assert result.http_status is None
    assert result.error_message is not None
    assert "timed out" in result.error_message.lower()
    assert str(LEGAL_TAGS_TIMEOUT_SECONDS) in result.error_message


def test_list_legal_tags_connection_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_get(**_: Any) -> Any:
        raise requests.exceptions.ConnectionError("dns")

    monkeypatch.setattr(legal_tags_module.requests, "get", fake_get)
    result = list_legal_tags(_connection(), token="t")
    assert result.ok is False
    assert "ConnectionError" in (result.error_message or "")


def test_list_legal_tags_outgoing_headers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured = _patch_get(
        monkeypatch,
        lambda **_: _FakeResponse(
            status_code=200, json_payload={"legalTags": []}
        ),
    )
    list_legal_tags(_connection(), token="bearer-abc")
    headers = captured[0]["headers"]
    assert headers["Authorization"] == "Bearer bearer-abc"
    assert headers["data-partition-id"] == "example-opendes"
    assert headers["Accept"] == "application/json"
    assert "Content-Type" not in headers
    assert captured[0]["timeout"] == LEGAL_TAGS_TIMEOUT_SECONDS
    assert captured[0]["allow_redirects"] is False


@pytest.mark.parametrize(
    "header_name",
    ["correlation-id", "X-Correlation-ID", "Request-Id", "X-Request-Id"],
)
def test_list_legal_tags_correlation_id_case_insensitive(
    monkeypatch: pytest.MonkeyPatch, header_name: str
) -> None:
    _patch_get(
        monkeypatch,
        lambda **_: _FakeResponse(
            status_code=200,
            headers={header_name: "corr-x"},
            json_payload={"legalTags": []},
        ),
    )
    result = list_legal_tags(_connection(), token="t")
    assert result.correlation_id == "corr-x"


@pytest.mark.parametrize("token", ["", "   ", "\t\n"])
def test_list_legal_tags_rejects_blank_token(token: str) -> None:
    with pytest.raises(ValueError, match="non-empty bearer token"):
        list_legal_tags(_connection(), token=token)


def test_list_legal_tags_rejects_invalid_connection() -> None:
    bad = ADMEConnection(
        endpoint="", tenant_id="", client_id="", data_partition_id=""
    )
    with pytest.raises(ValueError, match="ADME connection is incomplete"):
        list_legal_tags(bad, token="t")


# ===========================================================================
# get_legal_tag
# ===========================================================================


def test_get_legal_tag_happy_path(monkeypatch: pytest.MonkeyPatch) -> None:
    captured = _patch_get(
        monkeypatch,
        lambda **_: _FakeResponse(
            status_code=200,
            headers={"correlation-id": "corr-get-1"},
            json_payload=_LEGAL_TAG_DTO,
        ),
    )

    result = get_legal_tag(
        _connection(), token="t", name="opendes-public-usa-dataset"
    )

    assert isinstance(result, LegalTagDetailResult)
    assert result.ok is True
    assert result.http_status == 200
    assert result.tag is not None
    assert result.tag.name == "opendes-public-usa-dataset"
    assert result.tag.is_valid is True
    assert result.correlation_id == "corr-get-1"
    assert captured[0]["url"].endswith(
        f"{LEGAL_TAGS_PATH}/opendes-public-usa-dataset"
    )


def test_get_legal_tag_url_encodes_special_chars(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured = _patch_get(
        monkeypatch,
        lambda **_: _FakeResponse(status_code=200, json_payload={}),
    )
    weird = "my tag/with#special?chars"
    get_legal_tag(_connection(), token="t", name=weird)
    assert captured[0]["url"].endswith(
        f"{LEGAL_TAGS_PATH}/{quote(weird, safe='')}"
    )


@pytest.mark.parametrize("status_code", [401, 403, 404, 500])
def test_get_legal_tag_http_errors(
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

    result = get_legal_tag(_connection(), token="t", name="x")
    assert result.ok is False
    assert result.http_status == status_code
    assert result.tag is None
    assert result.error_message is not None
    assert f"boom {status_code}" in result.error_message


@pytest.mark.parametrize(
    "key", ["message", "detail", "error", "title"]
)
def test_get_legal_tag_error_message_extraction_keys(
    monkeypatch: pytest.MonkeyPatch, key: str
) -> None:
    _patch_get(
        monkeypatch,
        lambda **_: _FakeResponse(
            status_code=400, json_payload={key: f"boom-{key}"}
        ),
    )

    result = get_legal_tag(_connection(), token="t", name="x")
    assert result.error_message == f"boom-{key}"


def test_get_legal_tag_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_get(**_: Any) -> Any:
        raise requests.exceptions.Timeout("slow")

    monkeypatch.setattr(legal_tags_module.requests, "get", fake_get)
    result = get_legal_tag(_connection(), token="t", name="x")
    assert result.ok is False
    assert result.http_status is None
    assert "timed out" in (result.error_message or "").lower()


def test_get_legal_tag_connection_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_get(**_: Any) -> Any:
        raise requests.exceptions.ConnectionError("dns")

    monkeypatch.setattr(legal_tags_module.requests, "get", fake_get)
    result = get_legal_tag(_connection(), token="t", name="x")
    assert result.ok is False
    assert "ConnectionError" in (result.error_message or "")


def test_get_legal_tag_outgoing_headers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured = _patch_get(
        monkeypatch,
        lambda **_: _FakeResponse(status_code=200, json_payload={}),
    )
    get_legal_tag(_connection(), token="bearer-abc", name="x")
    headers = captured[0]["headers"]
    assert headers["Authorization"] == "Bearer bearer-abc"
    assert headers["data-partition-id"] == "example-opendes"
    assert headers["Accept"] == "application/json"
    assert "Content-Type" not in headers


@pytest.mark.parametrize("name", ["", "   ", "\t\n"])
def test_get_legal_tag_rejects_blank_name(name: str) -> None:
    with pytest.raises(ValueError, match="legal tag name"):
        get_legal_tag(_connection(), token="t", name=name)


@pytest.mark.parametrize("token", ["", "   "])
def test_get_legal_tag_rejects_blank_token(token: str) -> None:
    with pytest.raises(ValueError, match="non-empty bearer token"):
        get_legal_tag(_connection(), token=token, name="x")


# ===========================================================================
# create_legal_tag
# ===========================================================================


def test_create_legal_tag_happy_path(monkeypatch: pytest.MonkeyPatch) -> None:
    captured = _patch_post(
        monkeypatch,
        lambda **_: _FakeResponse(
            status_code=201,
            headers={"correlation-id": "corr-create-1"},
            json_payload=_LEGAL_TAG_DTO,
        ),
    )

    result = create_legal_tag(
        _connection(),
        token="t",
        name="opendes-public-usa-dataset",
        description="Public USA dataset",
        properties=_VALID_PROPERTIES,
    )

    assert isinstance(result, LegalTagDetailResult)
    assert result.ok is True
    assert result.http_status == 201
    assert result.tag is not None
    assert result.tag.name == "opendes-public-usa-dataset"
    assert result.correlation_id == "corr-create-1"
    # POST body MUST be {name, description, properties}.
    sent = captured[0]["json"]
    assert sent == {
        "name": "opendes-public-usa-dataset",
        "description": "Public USA dataset",
        "properties": _VALID_PROPERTIES,
    }
    assert captured[0]["url"].endswith(LEGAL_TAGS_PATH)


@pytest.mark.parametrize("status_code", [400, 401, 403, 404, 500])
def test_create_legal_tag_http_errors(
    monkeypatch: pytest.MonkeyPatch, status_code: int
) -> None:
    _patch_post(
        monkeypatch,
        lambda **_: _FakeResponse(
            status_code=status_code,
            json_payload={"message": f"boom {status_code}"},
        ),
    )

    result = create_legal_tag(
        _connection(),
        token="t",
        name="opendes-x",
        description="x",
        properties=_VALID_PROPERTIES,
    )
    assert result.ok is False
    assert result.http_status == status_code
    assert result.tag is None
    assert f"boom {status_code}" in (result.error_message or "")


def test_create_legal_tag_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_post(**_: Any) -> Any:
        raise requests.exceptions.Timeout("slow")

    monkeypatch.setattr(legal_tags_module.requests, "post", fake_post)
    result = create_legal_tag(
        _connection(),
        token="t",
        name="opendes-x",
        description="x",
        properties=_VALID_PROPERTIES,
    )
    assert result.ok is False
    assert "timed out" in (result.error_message or "").lower()


def test_create_legal_tag_connection_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_post(**_: Any) -> Any:
        raise requests.exceptions.ConnectionError("dns")

    monkeypatch.setattr(legal_tags_module.requests, "post", fake_post)
    result = create_legal_tag(
        _connection(),
        token="t",
        name="opendes-x",
        description="x",
        properties=_VALID_PROPERTIES,
    )
    assert result.ok is False
    assert "ConnectionError" in (result.error_message or "")


def test_create_legal_tag_outgoing_headers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured = _patch_post(
        monkeypatch,
        lambda **_: _FakeResponse(status_code=201, json_payload={}),
    )
    create_legal_tag(
        _connection(),
        token="bearer-abc",
        name="opendes-x",
        description="x",
        properties=_VALID_PROPERTIES,
    )
    headers = captured[0]["headers"]
    assert headers["Authorization"] == "Bearer bearer-abc"
    assert headers["data-partition-id"] == "example-opendes"
    assert headers["Accept"] == "application/json"
    assert headers["Content-Type"] == "application/json"
    assert captured[0]["timeout"] == LEGAL_TAGS_TIMEOUT_SECONDS
    assert captured[0]["allow_redirects"] is False


@pytest.mark.parametrize("name", ["", "   ", "\t\n"])
def test_create_legal_tag_rejects_blank_name(name: str) -> None:
    with pytest.raises(ValueError, match="legal tag name"):
        create_legal_tag(
            _connection(),
            token="t",
            name=name,
            description="x",
            properties=_VALID_PROPERTIES,
        )


@pytest.mark.parametrize("description", ["", "   ", "\t"])
def test_create_legal_tag_rejects_blank_description(
    description: str,
) -> None:
    with pytest.raises(ValueError, match="description"):
        create_legal_tag(
            _connection(),
            token="t",
            name="opendes-x",
            description=description,
            properties=_VALID_PROPERTIES,
        )


def test_create_legal_tag_rejects_empty_properties() -> None:
    with pytest.raises(ValueError, match="properties"):
        create_legal_tag(
            _connection(),
            token="t",
            name="opendes-x",
            description="x",
            properties={},
        )


def test_create_legal_tag_rejects_missing_required_property_keys() -> None:
    """ValueError must list every missing required properties key."""
    sparse = {"countryOfOrigin": ["US"]}  # missing 6 of 7 required keys
    with pytest.raises(ValueError, match="properties keys") as excinfo:
        create_legal_tag(
            _connection(),
            token="t",
            name="opendes-x",
            description="x",
            properties=sparse,
        )
    msg = str(excinfo.value)
    for missing_key in (
        "contractId",
        "originator",
        "dataType",
        "securityClassification",
        "personalData",
        "exportClassification",
    ):
        assert missing_key in msg


@pytest.mark.parametrize("token", ["", "   "])
def test_create_legal_tag_rejects_blank_token(token: str) -> None:
    with pytest.raises(ValueError, match="non-empty bearer token"):
        create_legal_tag(
            _connection(),
            token=token,
            name="opendes-x",
            description="x",
            properties=_VALID_PROPERTIES,
        )


# ===========================================================================
# update_legal_tag
# ===========================================================================


def test_update_legal_tag_happy_path(monkeypatch: pytest.MonkeyPatch) -> None:
    captured = _patch_put(
        monkeypatch,
        lambda **_: _FakeResponse(
            status_code=200,
            headers={"correlation-id": "corr-put-1"},
            json_payload=_LEGAL_TAG_DTO,
        ),
    )

    result = update_legal_tag(
        _connection(),
        token="t",
        name="opendes-public-usa-dataset",
        description="updated",
        properties=_VALID_PROPERTIES,
    )

    assert isinstance(result, LegalTagDetailResult)
    assert result.ok is True
    assert result.http_status == 200
    assert result.tag is not None
    sent = captured[0]["json"]
    # Body contains name, description, properties — Satya's nested shape.
    assert sent["name"] == "opendes-public-usa-dataset"
    assert sent["description"] == "updated"
    assert sent["properties"] == _VALID_PROPERTIES


def test_update_legal_tag_only_passes_supplied_properties(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The page restricts the editable surface; the service forwards verbatim."""
    captured = _patch_put(
        monkeypatch,
        lambda **_: _FakeResponse(status_code=200, json_payload={}),
    )
    mutable_subset = {
        "contractId": "Renewal-2026",
        "expirationDate": "2030-01-01",
    }
    update_legal_tag(
        _connection(),
        token="t",
        name="opendes-x",
        description="renewed",
        properties=mutable_subset,
    )
    assert captured[0]["json"]["properties"] == mutable_subset


@pytest.mark.parametrize("status_code", [400, 401, 403, 404, 500])
def test_update_legal_tag_http_errors(
    monkeypatch: pytest.MonkeyPatch, status_code: int
) -> None:
    _patch_put(
        monkeypatch,
        lambda **_: _FakeResponse(
            status_code=status_code,
            json_payload={"message": f"boom {status_code}"},
        ),
    )

    result = update_legal_tag(
        _connection(),
        token="t",
        name="opendes-x",
        description="x",
        properties=_VALID_PROPERTIES,
    )
    assert result.ok is False
    assert result.http_status == status_code
    assert f"boom {status_code}" in (result.error_message or "")


def test_update_legal_tag_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_put(**_: Any) -> Any:
        raise requests.exceptions.Timeout("slow")

    monkeypatch.setattr(legal_tags_module.requests, "put", fake_put)
    result = update_legal_tag(
        _connection(),
        token="t",
        name="opendes-x",
        description="x",
        properties=_VALID_PROPERTIES,
    )
    assert result.ok is False
    assert "timed out" in (result.error_message or "").lower()


def test_update_legal_tag_connection_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_put(**_: Any) -> Any:
        raise requests.exceptions.ConnectionError("dns")

    monkeypatch.setattr(legal_tags_module.requests, "put", fake_put)
    result = update_legal_tag(
        _connection(),
        token="t",
        name="opendes-x",
        description="x",
        properties=_VALID_PROPERTIES,
    )
    assert result.ok is False
    assert "ConnectionError" in (result.error_message or "")


def test_update_legal_tag_outgoing_headers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured = _patch_put(
        monkeypatch,
        lambda **_: _FakeResponse(status_code=200, json_payload={}),
    )
    update_legal_tag(
        _connection(),
        token="bearer-abc",
        name="opendes-x",
        description="x",
        properties=_VALID_PROPERTIES,
    )
    headers = captured[0]["headers"]
    assert headers["Authorization"] == "Bearer bearer-abc"
    assert headers["data-partition-id"] == "example-opendes"
    assert headers["Accept"] == "application/json"
    assert headers["Content-Type"] == "application/json"


@pytest.mark.parametrize("name", ["", "   ", "\t"])
def test_update_legal_tag_rejects_blank_name(name: str) -> None:
    with pytest.raises(ValueError, match="legal tag name"):
        update_legal_tag(
            _connection(),
            token="t",
            name=name,
            description="x",
            properties=_VALID_PROPERTIES,
        )


@pytest.mark.parametrize("description", ["", "   "])
def test_update_legal_tag_rejects_blank_description(description: str) -> None:
    with pytest.raises(ValueError, match="description"):
        update_legal_tag(
            _connection(),
            token="t",
            name="opendes-x",
            description=description,
            properties=_VALID_PROPERTIES,
        )


def test_update_legal_tag_rejects_empty_properties() -> None:
    with pytest.raises(ValueError, match="properties"):
        update_legal_tag(
            _connection(),
            token="t",
            name="opendes-x",
            description="x",
            properties={},
        )


# ===========================================================================
# delete_legal_tag
# ===========================================================================


def test_delete_legal_tag_happy_path(monkeypatch: pytest.MonkeyPatch) -> None:
    captured = _patch_delete(
        monkeypatch,
        lambda **_: _FakeResponse(
            status_code=204,
            headers={"correlation-id": "corr-del-1"},
            body="",
            raise_on_json=True,
        ),
    )

    result = delete_legal_tag(
        _connection(), token="t", name="opendes-public-usa-dataset"
    )

    assert isinstance(result, LegalTagOperationResult)
    assert result.ok is True
    assert result.http_status == 204
    assert result.name == "opendes-public-usa-dataset"
    assert result.correlation_id == "corr-del-1"
    assert captured[0]["url"].endswith(
        f"{LEGAL_TAGS_PATH}/opendes-public-usa-dataset"
    )


def test_delete_legal_tag_404_uses_curated_message(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_delete(
        monkeypatch,
        lambda **_: _FakeResponse(
            status_code=404, json_payload={"message": "raw not found"}
        ),
    )

    result = delete_legal_tag(
        _connection(data_partition_id="opendes"),
        token="t",
        name="missing-tag",
    )
    assert result.ok is False
    assert result.http_status == 404
    assert result.error_message is not None
    assert "missing-tag" in result.error_message
    assert "opendes" in result.error_message
    assert "not found" in result.error_message.lower()


@pytest.mark.parametrize("status_code", [401, 403, 500])
def test_delete_legal_tag_http_errors(
    monkeypatch: pytest.MonkeyPatch, status_code: int
) -> None:
    _patch_delete(
        monkeypatch,
        lambda **_: _FakeResponse(
            status_code=status_code,
            json_payload={"message": f"boom {status_code}"},
        ),
    )

    result = delete_legal_tag(_connection(), token="t", name="x")
    assert result.ok is False
    assert result.http_status == status_code
    assert f"boom {status_code}" in (result.error_message or "")


def test_delete_legal_tag_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_delete(**_: Any) -> Any:
        raise requests.exceptions.Timeout("slow")

    monkeypatch.setattr(legal_tags_module.requests, "delete", fake_delete)
    result = delete_legal_tag(_connection(), token="t", name="x")
    assert result.ok is False
    assert result.http_status is None
    assert "timed out" in (result.error_message or "").lower()


def test_delete_legal_tag_connection_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_delete(**_: Any) -> Any:
        raise requests.exceptions.ConnectionError("dns")

    monkeypatch.setattr(legal_tags_module.requests, "delete", fake_delete)
    result = delete_legal_tag(_connection(), token="t", name="x")
    assert result.ok is False
    assert "ConnectionError" in (result.error_message or "")


def test_delete_legal_tag_outgoing_headers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured = _patch_delete(
        monkeypatch,
        lambda **_: _FakeResponse(status_code=204, raise_on_json=True),
    )
    delete_legal_tag(_connection(), token="bearer-abc", name="x")
    headers = captured[0]["headers"]
    assert headers["Authorization"] == "Bearer bearer-abc"
    assert headers["data-partition-id"] == "example-opendes"
    assert headers["Accept"] == "application/json"
    assert "Content-Type" not in headers


def test_delete_legal_tag_url_encodes_special_chars(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured = _patch_delete(
        monkeypatch,
        lambda **_: _FakeResponse(status_code=204, raise_on_json=True),
    )
    weird = "a tag/with spaces+and-slash"
    delete_legal_tag(_connection(), token="t", name=weird)
    assert captured[0]["url"].endswith(
        f"{LEGAL_TAGS_PATH}/{quote(weird, safe='')}"
    )


@pytest.mark.parametrize("name", ["", "   ", "\t"])
def test_delete_legal_tag_rejects_blank_name(name: str) -> None:
    with pytest.raises(ValueError, match="legal tag name"):
        delete_legal_tag(_connection(), token="t", name=name)


@pytest.mark.parametrize("token", ["", "   "])
def test_delete_legal_tag_rejects_blank_token(token: str) -> None:
    with pytest.raises(ValueError, match="non-empty bearer token"):
        delete_legal_tag(_connection(), token=token, name="x")


# ===========================================================================
# get_legal_tag_properties
# ===========================================================================


def test_get_legal_tag_properties_happy_path_dict_countries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Per Darryl A.7, countries come back as a dict (alpha-2 → display name)."""
    captured = _patch_get(
        monkeypatch,
        lambda **_: _FakeResponse(
            status_code=200,
            headers={"correlation-id": "corr-props-1"},
            json_payload={
                "countriesOfOrigin": {
                    "AU": "Australia",
                    "US": "United States of America",
                    "CA": "Canada",
                },
                "otherRelevantDataCountries": {"GB": "United Kingdom"},
                "dataTypes": [
                    "Public Domain Data",
                    "First Party Data",
                    "Second Party Data",
                ],
                "securityClassifications": ["Public", "Private", "Confidential"],
                "exportClassificationControlNumbers": ["EAR99", "0A998"],
                "personalDataTypes": [
                    "Personally Identifiable",
                    "No Personal Data",
                ],
            },
        ),
    )

    result = get_legal_tag_properties(_connection(), token="t")

    assert isinstance(result, LegalTagPropertiesResult)
    assert result.ok is True
    assert result.http_status == 200
    assert result.spec is not None
    spec = result.spec
    # Dict countries surface as sorted alpha-2 keys.
    assert spec.country_of_origin == ["AU", "CA", "US"]
    assert spec.other_relevant_data_countries == ["GB"]
    assert spec.data_types == [
        "Public Domain Data",
        "First Party Data",
        "Second Party Data",
    ]
    assert spec.security_classifications == ["Public", "Private", "Confidential"]
    assert spec.export_classifications == ["EAR99", "0A998"]
    assert spec.personal_data_types == [
        "Personally Identifiable",
        "No Personal Data",
    ]
    assert result.correlation_id == "corr-props-1"
    # Path uses the colon-separated OSDU convention (Darryl A.7).
    assert captured[0]["url"].endswith(LEGAL_TAG_PROPERTIES_PATH)
    assert ":properties" in captured[0]["url"]


def test_get_legal_tag_properties_happy_path_list_classifications(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Older / Satya-spec response also accepted: list-of-strings everywhere."""
    _patch_get(
        monkeypatch,
        lambda **_: _FakeResponse(
            status_code=200,
            json_payload={
                "countryOfOrigin": ["US", "CA"],
                "exportClassifications": ["EAR99"],
                "dataTypes": ["Public Domain Data"],
                "securityClassifications": ["Public"],
                "personalDataTypes": ["No Personal Data"],
            },
        ),
    )

    result = get_legal_tag_properties(_connection(), token="t")
    assert result.ok is True
    assert result.spec is not None
    # Singular `countryOfOrigin` list shape accepted via fallback chain.
    assert result.spec.country_of_origin == ["US", "CA"]
    assert result.spec.export_classifications == ["EAR99"]


def test_get_legal_tag_properties_404_returns_ok_false_spec_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """404 is the fallback signal — spec=None, ok=False, http_status=404."""
    _patch_get(
        monkeypatch,
        lambda **_: _FakeResponse(
            status_code=404,
            headers={"correlation-id": "corr-404"},
            json_payload={"message": "no properties endpoint here"},
        ),
    )

    result = get_legal_tag_properties(_connection(), token="t")
    assert result.ok is False
    assert result.http_status == 404
    assert result.spec is None
    assert result.error_message is not None
    assert "no properties endpoint here" in result.error_message


@pytest.mark.parametrize("status_code", [401, 403, 500])
def test_get_legal_tag_properties_http_errors(
    monkeypatch: pytest.MonkeyPatch, status_code: int
) -> None:
    _patch_get(
        monkeypatch,
        lambda **_: _FakeResponse(
            status_code=status_code,
            json_payload={"message": f"boom {status_code}"},
        ),
    )

    result = get_legal_tag_properties(_connection(), token="t")
    assert result.ok is False
    assert result.http_status == status_code
    assert result.spec is None


def test_get_legal_tag_properties_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_get(**_: Any) -> Any:
        raise requests.exceptions.Timeout("slow")

    monkeypatch.setattr(legal_tags_module.requests, "get", fake_get)
    result = get_legal_tag_properties(_connection(), token="t")
    assert result.ok is False
    assert result.http_status is None
    assert "timed out" in (result.error_message or "").lower()


def test_get_legal_tag_properties_connection_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_get(**_: Any) -> Any:
        raise requests.exceptions.ConnectionError("dns")

    monkeypatch.setattr(legal_tags_module.requests, "get", fake_get)
    result = get_legal_tag_properties(_connection(), token="t")
    assert result.ok is False
    assert "ConnectionError" in (result.error_message or "")


def test_get_legal_tag_properties_non_list_dict_values_degrade_to_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Non-list, non-dict values silently degrade to empty list (no raise)."""
    _patch_get(
        monkeypatch,
        lambda **_: _FakeResponse(
            status_code=200,
            json_payload={
                "countriesOfOrigin": "not a list or dict",
                "dataTypes": 42,
                "securityClassifications": None,
            },
        ),
    )

    result = get_legal_tag_properties(_connection(), token="t")
    assert result.ok is True
    assert result.spec is not None
    assert result.spec.country_of_origin == []
    assert result.spec.data_types == []
    assert result.spec.security_classifications == []


def test_get_legal_tag_properties_outgoing_headers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured = _patch_get(
        monkeypatch,
        lambda **_: _FakeResponse(status_code=200, json_payload={}),
    )
    get_legal_tag_properties(_connection(), token="bearer-abc")
    headers = captured[0]["headers"]
    assert headers["Authorization"] == "Bearer bearer-abc"
    assert headers["data-partition-id"] == "example-opendes"
    assert headers["Accept"] == "application/json"
    assert "Content-Type" not in headers


@pytest.mark.parametrize("token", ["", "   "])
def test_get_legal_tag_properties_rejects_blank_token(token: str) -> None:
    with pytest.raises(ValueError, match="non-empty bearer token"):
        get_legal_tag_properties(_connection(), token=token)


def test_get_legal_tag_properties_rejects_invalid_connection() -> None:
    bad = ADMEConnection(
        endpoint="", tenant_id="", client_id="", data_partition_id=""
    )
    with pytest.raises(ValueError, match="ADME connection is incomplete"):
        get_legal_tag_properties(bad, token="t")


# ===========================================================================
# Cross-function: trailing-slash endpoint stripping (uses _call_legal seam)
# ===========================================================================


def test_endpoint_trailing_slash_is_stripped(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured = _patch_get(
        monkeypatch,
        lambda **_: _FakeResponse(
            status_code=200, json_payload={"legalTags": []}
        ),
    )
    list_legal_tags(
        _connection(endpoint="https://example.energy.azure.com/"),
        token="t",
    )
    assert captured[0]["url"] == (
        "https://example.energy.azure.com" + LEGAL_TAGS_PATH
    )
