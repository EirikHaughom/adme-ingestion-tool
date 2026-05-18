"""ADME Legal Service (legal tags) API client.

Sibling to :mod:`app.services.entitlements` and :mod:`app.services.ingestion`:
stdlib + ``requests`` only, a 5-second per-call timeout, and *no internal
retries* — the Streamlit page owns re-run UX. Each public function returns
a frozen result dataclass from :mod:`app.models.osdu` describing exactly
what happened, including a server-supplied correlation identifier when
one is present.

This module is the single source of truth for ``LEGAL_TAGS_PATH``;
``app/services/ingestion.py`` re-exports the constant for the ingestion
pre-flight ``check_legal_tag`` probe.
"""

from __future__ import annotations

from collections.abc import Iterable
from time import perf_counter
from typing import Any
from urllib.parse import quote

import requests  # type: ignore[import-untyped]

from app.models.connection import ADMEConnection
from app.models.osdu import (
    LegalTag,
    LegalTagDetailResult,
    LegalTagListResult,
    LegalTagOperationResult,
    LegalTagPropertiesResult,
    LegalTagPropertiesSpec,
)

LEGAL_TAGS_TIMEOUT_SECONDS = 5

LEGAL_TAGS_PATH = "/api/legal/v1/legaltags"
# Per Darryl's verified controller research the properties endpoint is
# colon-separated, not a sub-path. Same for :validate. Satya's spec
# assumed slash-paths; Darryl's docs review wins (LegalTagApi.java).
LEGAL_TAG_PROPERTIES_PATH = "/api/legal/v1/legaltags:properties"
LEGAL_TAG_VALIDATE_PATH = "/api/legal/v1/legaltags:validate"

# Required keys inside ``properties`` on create, per Darryl's verified
# Section B "Required vs optional fields" table.
_REQUIRED_CREATE_PROPERTY_KEYS: tuple[str, ...] = (
    "countryOfOrigin",
    "contractId",
    "originator",
    "dataType",
    "securityClassification",
    "personalData",
    "exportClassification",
)

_CORRELATION_HEADER_NAMES: tuple[str, ...] = (
    "correlation-id",
    "x-correlation-id",
    "request-id",
    "x-request-id",
)

_ERROR_BODY_TEXT_LIMIT = 500


def list_legal_tags(
    connection: ADMEConnection,
    token: str,
    *,
    valid: bool | None = None,
) -> LegalTagListResult:
    """``GET /api/legal/v1/legaltags[?valid=true|false]``.

    ``valid=None`` omits the query string entirely (server default).
    """
    path = LEGAL_TAGS_PATH
    if valid is True:
        path = f"{LEGAL_TAGS_PATH}?valid=true"
    elif valid is False:
        path = f"{LEGAL_TAGS_PATH}?valid=false"

    parsed_body, http_status, correlation_id, latency_ms, error_message = (
        _call_legal(
            connection=connection,
            token=token,
            method="GET",
            path=path,
            json_body=None,
        )
    )

    if http_status is None:
        return LegalTagListResult(
            ok=False,
            http_status=None,
            latency_ms=latency_ms,
            correlation_id=None,
            error_message=error_message,
            raw_response=None,
        )

    if 200 <= http_status < 300:
        body = parsed_body if isinstance(parsed_body, dict) else {}
        raw_items = body.get("legalTags")
        items: list[LegalTag] = []
        if isinstance(raw_items, list):
            for entry in raw_items:
                if isinstance(entry, dict):
                    items.append(_parse_legal_tag(entry))
        return LegalTagListResult(
            items=items,
            ok=True,
            http_status=http_status,
            latency_ms=latency_ms,
            correlation_id=correlation_id,
            error_message=None,
            raw_response=parsed_body,
        )

    return LegalTagListResult(
        ok=False,
        http_status=http_status,
        latency_ms=latency_ms,
        correlation_id=correlation_id,
        error_message=error_message,
        raw_response=parsed_body,
    )


def get_legal_tag(
    connection: ADMEConnection,
    token: str,
    name: str,
) -> LegalTagDetailResult:
    """``GET /api/legal/v1/legaltags/{quoted_name}``."""
    if not name or not name.strip():
        raise ValueError(
            "A non-empty legal tag name is required for get_legal_tag."
        )

    quoted_name = quote(name, safe="")
    path = f"{LEGAL_TAGS_PATH}/{quoted_name}"

    parsed_body, http_status, correlation_id, latency_ms, error_message = (
        _call_legal(
            connection=connection,
            token=token,
            method="GET",
            path=path,
            json_body=None,
        )
    )

    return _build_detail_result(
        parsed_body=parsed_body,
        http_status=http_status,
        correlation_id=correlation_id,
        latency_ms=latency_ms,
        error_message=error_message,
    )


def create_legal_tag(
    connection: ADMEConnection,
    token: str,
    *,
    name: str,
    description: str,
    properties: dict[str, Any],
) -> LegalTagDetailResult:
    """``POST /api/legal/v1/legaltags``.

    Validates the seven required ``properties`` keys (countryOfOrigin,
    contractId, originator, dataType, securityClassification,
    personalData, exportClassification) before any HTTP work.
    """
    if not name or not name.strip():
        raise ValueError(
            "A non-empty legal tag name is required for create_legal_tag."
        )
    if not description or not description.strip():
        raise ValueError(
            "A non-empty description is required for create_legal_tag."
        )
    if not isinstance(properties, dict) or not properties:
        raise ValueError(
            "A non-empty properties dict is required for create_legal_tag."
        )
    missing = [
        key
        for key in _REQUIRED_CREATE_PROPERTY_KEYS
        if not _has_nonempty_value(properties.get(key))
    ]
    if missing:
        raise ValueError(
            "create_legal_tag is missing required properties keys: "
            + ", ".join(missing)
        )

    body = {
        "name": name,
        "description": description,
        "properties": properties,
    }

    parsed_body, http_status, correlation_id, latency_ms, error_message = (
        _call_legal(
            connection=connection,
            token=token,
            method="POST",
            path=LEGAL_TAGS_PATH,
            json_body=body,
        )
    )

    return _build_detail_result(
        parsed_body=parsed_body,
        http_status=http_status,
        correlation_id=correlation_id,
        latency_ms=latency_ms,
        error_message=error_message,
    )


def update_legal_tag(
    connection: ADMEConnection,
    token: str,
    *,
    name: str,
    description: str,
    properties: dict[str, Any],
) -> LegalTagDetailResult:
    """``PUT /api/legal/v1/legaltags``.

    Per Darryl's controller research only ``description``, ``contractId``,
    ``expirationDate``, and ``extensionProperties`` are mutable. We accept
    a partial ``properties`` dict and pass it through; callers (the page)
    are responsible for restricting the editable surface. Sends Satya's
    canonical body shape ``{name, description, properties}``.
    """
    if not name or not name.strip():
        raise ValueError(
            "A non-empty legal tag name is required for update_legal_tag."
        )
    if not description or not description.strip():
        raise ValueError(
            "A non-empty description is required for update_legal_tag."
        )
    if not isinstance(properties, dict) or not properties:
        raise ValueError(
            "A non-empty properties dict is required for update_legal_tag."
        )

    body = {
        "name": name,
        "description": description,
        "properties": properties,
    }

    parsed_body, http_status, correlation_id, latency_ms, error_message = (
        _call_legal(
            connection=connection,
            token=token,
            method="PUT",
            path=LEGAL_TAGS_PATH,
            json_body=body,
        )
    )

    return _build_detail_result(
        parsed_body=parsed_body,
        http_status=http_status,
        correlation_id=correlation_id,
        latency_ms=latency_ms,
        error_message=error_message,
    )


def delete_legal_tag(
    connection: ADMEConnection,
    token: str,
    name: str,
) -> LegalTagOperationResult:
    """``DELETE /api/legal/v1/legaltags/{quoted_name}`` (admin-only)."""
    if not name or not name.strip():
        raise ValueError(
            "A non-empty legal tag name is required for delete_legal_tag."
        )

    quoted_name = quote(name, safe="")
    path = f"{LEGAL_TAGS_PATH}/{quoted_name}"

    parsed_body, http_status, correlation_id, latency_ms, error_message = (
        _call_legal(
            connection=connection,
            token=token,
            method="DELETE",
            path=path,
            json_body=None,
        )
    )

    if http_status is None:
        return LegalTagOperationResult(
            name=name,
            ok=False,
            http_status=None,
            latency_ms=latency_ms,
            correlation_id=None,
            error_message=error_message,
            raw_response=None,
        )

    if 200 <= http_status < 300:
        return LegalTagOperationResult(
            name=name,
            ok=True,
            http_status=http_status,
            latency_ms=latency_ms,
            correlation_id=correlation_id,
            error_message=None,
            raw_response=parsed_body,
        )

    if http_status == 404:
        friendly = (
            f"Legal tag '{name}' not found in partition "
            f"'{connection.data_partition_id}'."
        )
        return LegalTagOperationResult(
            name=name,
            ok=False,
            http_status=http_status,
            latency_ms=latency_ms,
            correlation_id=correlation_id,
            error_message=friendly,
            raw_response=parsed_body,
        )

    return LegalTagOperationResult(
        name=name,
        ok=False,
        http_status=http_status,
        latency_ms=latency_ms,
        correlation_id=correlation_id,
        error_message=error_message,
        raw_response=parsed_body,
    )


def get_legal_tag_properties(
    connection: ADMEConnection,
    token: str,
) -> LegalTagPropertiesResult:
    """``GET /api/legal/v1/legaltags:properties``.

    On 404 the page should fall back to hardcoded defaults — this
    function returns ``ok=False, http_status=404, spec=None`` so the
    page can detect that branch (per Satya's contract section 3
    fallback rule).
    """
    parsed_body, http_status, correlation_id, latency_ms, error_message = (
        _call_legal(
            connection=connection,
            token=token,
            method="GET",
            path=LEGAL_TAG_PROPERTIES_PATH,
            json_body=None,
        )
    )

    if http_status is None:
        return LegalTagPropertiesResult(
            spec=None,
            ok=False,
            http_status=None,
            latency_ms=latency_ms,
            correlation_id=None,
            error_message=error_message,
            raw_response=None,
        )

    if 200 <= http_status < 300:
        body = parsed_body if isinstance(parsed_body, dict) else {}
        spec = _parse_properties_spec(body)
        return LegalTagPropertiesResult(
            spec=spec,
            ok=True,
            http_status=http_status,
            latency_ms=latency_ms,
            correlation_id=correlation_id,
            error_message=None,
            raw_response=parsed_body,
        )

    return LegalTagPropertiesResult(
        spec=None,
        ok=False,
        http_status=http_status,
        latency_ms=latency_ms,
        correlation_id=correlation_id,
        error_message=error_message,
        raw_response=parsed_body,
    )


# --- internal helpers ---------------------------------------------------


def _build_detail_result(
    *,
    parsed_body: dict | str | None,
    http_status: int | None,
    correlation_id: str | None,
    latency_ms: float,
    error_message: str | None,
) -> LegalTagDetailResult:
    if http_status is None:
        return LegalTagDetailResult(
            tag=None,
            ok=False,
            http_status=None,
            latency_ms=latency_ms,
            correlation_id=None,
            error_message=error_message,
            raw_response=None,
        )

    if 200 <= http_status < 300:
        body = parsed_body if isinstance(parsed_body, dict) else {}
        tag = _parse_legal_tag(body) if body else None
        return LegalTagDetailResult(
            tag=tag,
            ok=True,
            http_status=http_status,
            latency_ms=latency_ms,
            correlation_id=correlation_id,
            error_message=None,
            raw_response=parsed_body,
        )

    return LegalTagDetailResult(
        tag=None,
        ok=False,
        http_status=http_status,
        latency_ms=latency_ms,
        correlation_id=correlation_id,
        error_message=error_message,
        raw_response=parsed_body,
    )


def _parse_legal_tag(payload: dict) -> LegalTag:
    name_raw = payload.get("name", "")
    name = name_raw if isinstance(name_raw, str) else ""
    description_raw = payload.get("description", "")
    description = description_raw if isinstance(description_raw, str) else ""
    properties_raw = payload.get("properties", {})
    properties: dict[str, Any] = (
        dict(properties_raw) if isinstance(properties_raw, dict) else {}
    )
    is_valid_raw = payload.get("isValid")
    is_valid: bool | None = (
        is_valid_raw if isinstance(is_valid_raw, bool) else None
    )
    return LegalTag(
        name=name,
        description=description,
        properties=properties,
        is_valid=is_valid,
    )


def _parse_properties_spec(payload: dict) -> LegalTagPropertiesSpec:
    """Normalize the partition's allowed-values payload.

    Darryl's Section A.7 verified that countries are returned as a dict
    (alpha-2 → display name) while classifications are arrays. Satya's
    contract assumed everything was a list. We accept BOTH shapes:
    dicts surface as their sorted key list, lists pass through, anything
    else degrades to an empty list (do not raise).
    """
    return LegalTagPropertiesSpec(
        country_of_origin=_coerce_string_collection(
            payload.get("countriesOfOrigin"),
            payload.get("countryOfOrigin"),
        ),
        other_relevant_data_countries=_coerce_string_collection(
            payload.get("otherRelevantDataCountries"),
        ),
        security_classifications=_coerce_string_collection(
            payload.get("securityClassifications"),
        ),
        export_classifications=_coerce_string_collection(
            # Darryl confirmed the controller returns
            # `exportClassificationControlNumbers`; older docs used
            # `exportClassifications`. Accept either.
            payload.get("exportClassificationControlNumbers"),
            payload.get("exportClassifications"),
        ),
        personal_data_types=_coerce_string_collection(
            payload.get("personalDataTypes"),
        ),
        data_types=_coerce_string_collection(
            payload.get("dataTypes"),
        ),
    )


def _coerce_string_collection(*candidates: object) -> list[str]:
    for candidate in candidates:
        if candidate is None:
            continue
        if isinstance(candidate, list):
            return [item for item in candidate if isinstance(item, str)]
        if isinstance(candidate, dict):
            return sorted(
                key for key in candidate.keys() if isinstance(key, str)
            )
    return []


def _has_nonempty_value(value: object) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, list | tuple | set | dict):
        return len(value) > 0
    return True


def _call_legal(
    connection: ADMEConnection,
    token: str,
    *,
    method: str,
    path: str,
    json_body: dict | None,
) -> tuple[dict | str | None, int | None, str | None, float, str | None]:
    if not connection.is_valid():
        raise ValueError(
            "ADME connection is incomplete. Endpoint, tenant ID, "
            "client ID, and data partition ID are required. Service "
            "principal auth also requires a client secret."
        )
    if not token.strip():
        raise ValueError(
            "A non-empty bearer token is required for legal tag calls."
        )

    url = f"{connection.endpoint.rstrip('/')}{path}"
    headers = {
        "Authorization": f"Bearer {token}",
        "data-partition-id": connection.data_partition_id,
        "Accept": "application/json",
    }
    if json_body is not None:
        headers["Content-Type"] = "application/json"

    started_at = perf_counter()

    try:
        if method == "GET":
            response = requests.get(
                url=url,
                headers=headers,
                timeout=LEGAL_TAGS_TIMEOUT_SECONDS,
                allow_redirects=False,
            )
        elif method == "POST":
            response = requests.post(
                url=url,
                headers=headers,
                json=json_body,
                timeout=LEGAL_TAGS_TIMEOUT_SECONDS,
                allow_redirects=False,
            )
        elif method == "PUT":
            response = requests.put(
                url=url,
                headers=headers,
                json=json_body,
                timeout=LEGAL_TAGS_TIMEOUT_SECONDS,
                allow_redirects=False,
            )
        elif method == "DELETE":
            response = requests.delete(
                url=url,
                headers=headers,
                timeout=LEGAL_TAGS_TIMEOUT_SECONDS,
                allow_redirects=False,
            )
        else:
            raise ValueError(f"Unsupported HTTP method: {method}")
    except requests.Timeout:
        return (
            None,
            None,
            None,
            _elapsed_ms(started_at),
            f"Request timed out after {LEGAL_TAGS_TIMEOUT_SECONDS}s",
        )
    except requests.RequestException as exc:
        return (
            None,
            None,
            None,
            _elapsed_ms(started_at),
            f"{type(exc).__name__}: {exc}",
        )
    except Exception as exc:  # pragma: no cover - defensive boundary
        return (
            None,
            None,
            None,
            _elapsed_ms(started_at),
            f"{type(exc).__name__}: {exc}",
        )

    latency_ms = _elapsed_ms(started_at)
    correlation_id = _extract_correlation_id(
        response.headers, _CORRELATION_HEADER_NAMES
    )
    parsed_body = _try_parse_json(response)

    if 200 <= response.status_code < 300:
        return (
            parsed_body,
            response.status_code,
            correlation_id,
            latency_ms,
            None,
        )

    if parsed_body is not None and isinstance(parsed_body, dict):
        error_message = _error_message_from_json(
            parsed_body, response.status_code
        )
        return (
            parsed_body,
            response.status_code,
            correlation_id,
            latency_ms,
            error_message,
        )

    text = getattr(response, "text", "") or ""
    body: dict | str | None = text if text else None
    error_message = (
        _truncate(text) if text else f"HTTP {response.status_code}"
    )
    return (
        body,
        response.status_code,
        correlation_id,
        latency_ms,
        error_message,
    )


def _elapsed_ms(started_at: float) -> float:
    return round((perf_counter() - started_at) * 1000, 2)


def _extract_correlation_id(
    headers: object,
    candidate_names: Iterable[str],
) -> str | None:
    if headers is None:
        return None
    lowercase_lookup: dict[str, str] = {}
    try:
        items = headers.items()  # type: ignore[attr-defined]
    except AttributeError:
        return None
    for key, value in items:
        if isinstance(key, str) and isinstance(value, str):
            lowercase_lookup[key.lower()] = value
    for name in candidate_names:
        value = lowercase_lookup.get(name.lower())
        if value:
            return value
    return None


def _try_parse_json(response: requests.Response) -> dict | None:
    response_json = getattr(response, "json", None)
    if not callable(response_json):
        return None
    try:
        payload = response_json()
    except ValueError:
        return None
    if isinstance(payload, dict):
        return payload
    return None


def _error_message_from_json(payload: dict, status_code: int) -> str:
    for key in ("message", "detail", "error", "title"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return _truncate(value)

    errors = payload.get("errors")
    if isinstance(errors, list) and errors:
        return _truncate(str(errors[0]))
    if isinstance(errors, dict) and errors:
        first_value = next(iter(errors.values()))
        return _truncate(str(first_value))

    return f"HTTP {status_code}"


def _truncate(value: str, limit: int = _ERROR_BODY_TEXT_LIMIT) -> str:
    collapsed = " ".join(value.split())
    if len(collapsed) <= limit:
        return collapsed
    return f"{collapsed[: limit - 3]}..."
