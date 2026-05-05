"""ADME Entitlements API smoke-test calls.

This module is the operator's "does my token actually work as me" probe.
It is a sibling to :mod:`app.services.health`: stdlib + ``requests``
only, a 5-second timeout, and *no internal retries* — the Streamlit
page owns re-run UX.  Both functions return an
:class:`~app.models.connection.EntitlementsCallResult` describing exactly
what happened, including a server-supplied correlation identifier when
one is present on the response.
"""

from __future__ import annotations

from collections.abc import Iterable
from time import perf_counter

import requests  # type: ignore[import-untyped]

from app.models.connection import ADMEConnection, EntitlementsCallResult

ENTITLEMENTS_TIMEOUT_SECONDS = 5

MEMBERS_SELF_ENDPOINT_LABEL = "members.self"
GROUPS_ENDPOINT_LABEL = "groups"

MEMBERS_SELF_PATH = "/api/entitlements/v2/members/me"
GROUPS_PATH = "/api/entitlements/v2/groups"

# Probed in order; the first header that is present wins.  ADME and any
# proxies in front of it may use different casings, so the lookup itself
# is case-insensitive.
_CORRELATION_HEADER_NAMES: tuple[str, ...] = (
    "correlation-id",
    "x-correlation-id",
    "request-id",
    "x-request-id",
)

_ERROR_BODY_TEXT_LIMIT = 500


def fetch_member_self(
    connection: ADMEConnection,
    token: str,
) -> EntitlementsCallResult:
    """Call ``GET /api/entitlements/v2/members/me`` and return the result."""
    return _call_entitlements(
        connection=connection,
        token=token,
        endpoint_label=MEMBERS_SELF_ENDPOINT_LABEL,
        path=MEMBERS_SELF_PATH,
    )


def fetch_groups(
    connection: ADMEConnection,
    token: str,
) -> EntitlementsCallResult:
    """Call ``GET /api/entitlements/v2/groups`` and return the result."""
    return _call_entitlements(
        connection=connection,
        token=token,
        endpoint_label=GROUPS_ENDPOINT_LABEL,
        path=GROUPS_PATH,
    )


def _call_entitlements(
    connection: ADMEConnection,
    token: str,
    endpoint_label: str,
    path: str,
) -> EntitlementsCallResult:
    if not connection.is_valid():
        raise ValueError(
            "ADME connection is incomplete. Endpoint, tenant ID, client ID, and "
            "data partition ID are required. Service principal auth also requires "
            "a client secret."
        )
    if not token.strip():
        raise ValueError(
            "A non-empty bearer token is required for entitlements calls."
        )

    url = f"{connection.endpoint.rstrip('/')}{path}"
    headers = {
        "Authorization": f"Bearer {token}",
        "data-partition-id": connection.data_partition_id,
        "Accept": "application/json",
    }
    started_at = perf_counter()

    try:
        response = requests.get(
            url=url,
            headers=headers,
            timeout=ENTITLEMENTS_TIMEOUT_SECONDS,
            allow_redirects=False,
        )
    except requests.Timeout:
        return EntitlementsCallResult(
            endpoint=endpoint_label,
            path=path,
            ok=False,
            http_status=None,
            latency_ms=_elapsed_ms(started_at),
            correlation_id=None,
            error_message=(
                f"Request timed out after {ENTITLEMENTS_TIMEOUT_SECONDS}s"
            ),
            raw_response=None,
            data=None,
        )
    except requests.RequestException as exc:
        return EntitlementsCallResult(
            endpoint=endpoint_label,
            path=path,
            ok=False,
            http_status=None,
            latency_ms=_elapsed_ms(started_at),
            correlation_id=None,
            error_message=f"{type(exc).__name__}: {exc}",
            raw_response=None,
            data=None,
        )
    except Exception as exc:  # pragma: no cover - defensive boundary
        return EntitlementsCallResult(
            endpoint=endpoint_label,
            path=path,
            ok=False,
            http_status=None,
            latency_ms=_elapsed_ms(started_at),
            correlation_id=None,
            error_message=f"{type(exc).__name__}: {exc}",
            raw_response=None,
            data=None,
        )

    latency_ms = _elapsed_ms(started_at)
    correlation_id = _extract_correlation_id(
        response.headers, _CORRELATION_HEADER_NAMES
    )
    parsed_body = _try_parse_json(response)

    if 200 <= response.status_code < 300:
        data = parsed_body if isinstance(parsed_body, dict) else None
        return EntitlementsCallResult(
            endpoint=endpoint_label,
            path=path,
            ok=True,
            http_status=response.status_code,
            latency_ms=latency_ms,
            correlation_id=correlation_id,
            error_message=None,
            raw_response=data,
            data=data,
        )

    if parsed_body is not None:
        raw_response: dict | str | None = parsed_body
        error_message = _error_message_from_json(parsed_body, response.status_code)
    else:
        text = getattr(response, "text", "") or ""
        raw_response = text if text else None
        error_message = _truncate(text) if text else f"HTTP {response.status_code}"

    return EntitlementsCallResult(
        endpoint=endpoint_label,
        path=path,
        ok=False,
        http_status=response.status_code,
        latency_ms=latency_ms,
        correlation_id=correlation_id,
        error_message=error_message,
        raw_response=raw_response,
        data=None,
    )


def _elapsed_ms(started_at: float) -> float:
    return round((perf_counter() - started_at) * 1000, 2)


def _extract_correlation_id(
    headers: object,
    candidate_names: Iterable[str],
) -> str | None:
    if headers is None:
        return None
    # ``requests.Response.headers`` is a CaseInsensitiveDict, but probe the
    # keys directly so we tolerate any mapping-like object (and any casing
    # an upstream proxy might emit) without depending on that detail.
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
