"""ADME post-ingest verification calls.

Sibling to :mod:`app.services.ingestion`: stdlib + ``requests`` only,
a 5-second per-call timeout, no internal retries. The Streamlit page
owns retry / re-run UX (including the indexing-delay backoff).
"""

from __future__ import annotations

import logging
from collections.abc import Iterable
from time import perf_counter

import requests  # type: ignore[import-untyped]

from app.models.connection import ADMEConnection
from app.models.osdu import SearchResult

logger = logging.getLogger(__name__)

VERIFICATION_TIMEOUT_SECONDS = 5

SEARCH_QUERY_PATH = "/api/search/v2/query"
DEFAULT_SEARCH_LIMIT = 100

_CORRELATION_HEADER_NAMES: tuple[str, ...] = (
    "correlation-id",
    "x-correlation-id",
    "request-id",
    "x-request-id",
)

_ERROR_BODY_TEXT_LIMIT = 500


def search_records_by_kind(
    connection: ADMEConnection,
    token: str,
    kind: str,
    limit: int = DEFAULT_SEARCH_LIMIT,
) -> SearchResult:
    """Probe ``POST /api/search/v2/query`` for records of ``kind``.

    Returns a :class:`SearchResult` with ``count`` taken from the
    server's ``totalCount`` (falling back to ``len(results)``) and
    ``records`` filtered to dict items only. Transport failures return
    ``ok=False`` with ``http_status=None`` and never raise.
    """
    if not kind or not kind.strip():
        raise ValueError(
            "A non-empty kind is required for search_records_by_kind."
        )
    if limit < 1:
        raise ValueError("limit must be >= 1.")

    parsed_body, http_status, correlation_id, latency_ms, error_message = (
        _call_search(
            connection=connection,
            token=token,
            json_body={"kind": kind, "limit": limit, "offset": 0},
        )
    )

    if http_status is None:
        return SearchResult(
            kind=kind,
            count=0,
            records=[],
            ok=False,
            http_status=None,
            latency_ms=latency_ms,
            correlation_id=None,
            error_message=error_message,
        )

    if 200 <= http_status < 300:
        body = parsed_body if isinstance(parsed_body, dict) else {}
        raw_results = body.get("results", [])
        records: list[dict] = (
            [item for item in raw_results if isinstance(item, dict)]
            if isinstance(raw_results, list)
            else []
        )
        total_count_raw = body.get("totalCount")
        if isinstance(total_count_raw, int):
            count = total_count_raw
        else:
            count = len(records)
        return SearchResult(
            kind=kind,
            count=count,
            records=records,
            ok=True,
            http_status=http_status,
            latency_ms=latency_ms,
            correlation_id=correlation_id,
            error_message=None,
        )

    return SearchResult(
        kind=kind,
        count=0,
        records=[],
        ok=False,
        http_status=http_status,
        latency_ms=latency_ms,
        correlation_id=correlation_id,
        error_message=error_message,
    )


def _call_search(
    connection: ADMEConnection,
    token: str,
    json_body: dict,
) -> tuple[dict | str | None, int | None, str | None, float, str | None]:
    if not connection.is_valid():
        raise ValueError(
            "ADME connection is incomplete. Endpoint, tenant ID, "
            "client ID, and data partition ID are required. Service "
            "principal auth also requires a client secret."
        )
    if not token.strip():
        raise ValueError(
            "A non-empty bearer token is required for verification "
            "calls."
        )

    url = f"{connection.endpoint.rstrip('/')}{SEARCH_QUERY_PATH}"
    headers = {
        "Authorization": f"Bearer {token}",
        "data-partition-id": connection.data_partition_id,
        "Accept": "application/json",
        "Content-Type": "application/json",
    }
    started_at = perf_counter()

    try:
        response = requests.post(
            url=url,
            headers=headers,
            json=json_body,
            timeout=VERIFICATION_TIMEOUT_SECONDS,
            allow_redirects=False,
        )
    except requests.Timeout:
        return (
            None,
            None,
            None,
            _elapsed_ms(started_at),
            f"Request timed out after {VERIFICATION_TIMEOUT_SECONDS}s",
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
