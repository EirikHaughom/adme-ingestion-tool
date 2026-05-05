"""Health probes for Azure Data Manager for Energy OSDU services."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from time import perf_counter

import requests  # type: ignore[import-untyped]

from app.models.connection import OSDU_SERVICES, ADMEConnection, ServiceHealthResult

PROBE_TIMEOUT_SECONDS = 5
SEARCH_PROBE_BODY = {"kind": "*:*:*:*", "limit": 1}


def check_all(connection: ADMEConnection, token: str) -> list[ServiceHealthResult]:
    """Probe every configured OSDU service and return ordered health results."""
    if not connection.is_valid():
        raise ValueError(
            "ADME connection is incomplete. Endpoint, tenant ID, client ID, and "
            "data partition ID are required. Service principal auth also requires "
            "a client secret."
        )
    if not token.strip():
        raise ValueError("A non-empty bearer token is required for health checks.")

    results: list[ServiceHealthResult | None] = [None] * len(OSDU_SERVICES)
    with ThreadPoolExecutor(max_workers=max(1, len(OSDU_SERVICES))) as executor:
        future_to_service = {
            executor.submit(
                _probe_service,
                connection,
                token,
                service_name,
                path,
                method,
            ): (index, service_name, path)
            for index, (service_name, path, method) in enumerate(OSDU_SERVICES)
        }

        for future in as_completed(future_to_service):
            index, service_name, path = future_to_service[future]
            try:
                results[index] = future.result()
            except Exception as exc:
                error_message = (
                    f"Unexpected probe failure: {type(exc).__name__}: {exc}"
                )
                results[index] = ServiceHealthResult(
                    service_name=service_name,
                    path=path,
                    status="error",
                    status_code=None,
                    response_time_ms=0.0,
                    error_message=error_message,
                )

    return [result for result in results if result is not None]


def _probe_service(
    connection: ADMEConnection,
    token: str,
    service_name: str,
    path: str,
    method: str,
) -> ServiceHealthResult:
    url = f"{connection.endpoint.rstrip('/')}{path}"
    headers = {
        "Authorization": f"Bearer {token}",
        "data-partition-id": connection.data_partition_id,
    }
    started_at = perf_counter()

    try:
        response = requests.request(
            method=method,
            url=url,
            headers=headers,
            json=SEARCH_PROBE_BODY if method == "POST" else None,
            timeout=PROBE_TIMEOUT_SECONDS,
            allow_redirects=False,
        )
    except requests.Timeout:
        return ServiceHealthResult(
            service_name=service_name,
            path=path,
            status="error",
            status_code=None,
            response_time_ms=_elapsed_ms(started_at),
            error_message=f"Timed out after {PROBE_TIMEOUT_SECONDS} seconds.",
        )
    except requests.RequestException as exc:
        return ServiceHealthResult(
            service_name=service_name,
            path=path,
            status="error",
            status_code=None,
            response_time_ms=_elapsed_ms(started_at),
            error_message=_format_request_error(exc),
        )

    is_healthy = 200 <= response.status_code < 300
    error_message = ""
    if not is_healthy:
        error_message = _build_http_error_message(response)

    return ServiceHealthResult(
        service_name=service_name,
        path=path,
        status="healthy" if is_healthy else "unhealthy",
        status_code=response.status_code,
        response_time_ms=_elapsed_ms(started_at),
        error_message=error_message,
    )


def _elapsed_ms(started_at: float) -> float:
    return round((perf_counter() - started_at) * 1000, 2)


def _build_http_error_message(response: requests.Response) -> str:
    payload = None
    response_json = getattr(response, "json", None)
    if callable(response_json):
        try:
            payload = response_json()
        except ValueError:
            payload = None

    if isinstance(payload, dict):
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

    response_text = getattr(response, "text", "")
    text = " ".join(str(response_text).split())
    if text:
        return _truncate(text)
    response_reason = getattr(response, "reason", "")
    if response_reason:
        return str(response_reason)
    return f"HTTP {response.status_code}"


def _format_request_error(exc: requests.RequestException) -> str:
    message = str(exc).strip()
    if message:
        return message
    return type(exc).__name__


def _truncate(value: str, limit: int = 240) -> str:
    collapsed = " ".join(value.split())
    if len(collapsed) <= limit:
        return collapsed
    return f"{collapsed[: limit - 3]}..."
