"""ADME connection, health-check, and entitlements result models.

These dataclasses are the shared contract between the UI layer (Judson)
and the backend services (Kevin).  Health probes and entitlements smoke
tests both surface their results through dataclasses defined here so the
UI layer has a single import site for the contract.  Do not change field
names or types without updating both sides.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

ADME_RESOURCE_SCOPE = "https://energy.azure.com/.default"


class AuthMethod(StrEnum):
    """Supported authentication methods for ADME."""

    USER_IMPERSONATION = "user_impersonation"
    SERVICE_PRINCIPAL = "service_principal"


@dataclass
class ADMEConnection:
    """Everything needed to authenticate and talk to an ADME instance.

    Attributes:
        endpoint: ADME instance URL, e.g. ``https://myinstance.energy.azure.com``.
        tenant_id: Azure AD / Entra ID tenant GUID.
        client_id: App registration (client) ID used to authenticate with Entra ID.
        data_partition_id: OSDU data partition, e.g. ``myinstance-opendes``.
        token_scope: OAuth scope requested when acquiring ADME access tokens.
        auth_method: How the operator authenticates.
        client_secret: Required only when *auth_method* is SERVICE_PRINCIPAL.
    """

    endpoint: str
    tenant_id: str
    client_id: str
    data_partition_id: str
    token_scope: str = ADME_RESOURCE_SCOPE
    auth_method: AuthMethod = AuthMethod.USER_IMPERSONATION
    client_secret: str = ""

    @property
    def scope(self) -> str:
        """OAuth 2.0 scope requested for ADME tokens."""
        configured_scope = self.token_scope.strip()
        return configured_scope or ADME_RESOURCE_SCOPE

    def is_valid(self) -> bool:
        """Return True when all required fields are populated."""
        base_ok = bool(
            self.endpoint
            and self.tenant_id
            and self.client_id
            and self.data_partition_id
        )
        if self.auth_method == AuthMethod.SERVICE_PRINCIPAL:
            return base_ok and bool(self.client_secret)
        return base_ok


@dataclass
class ServiceHealthResult:
    """Outcome of a single OSDU service health probe.

    Attributes:
        service_name: Human-readable service name (e.g. ``Storage``).
        path: API path that was probed (e.g. ``/api/storage/v2/query/kinds``).
        status: ``healthy``, ``unhealthy``, or ``error``.
        status_code: HTTP status code returned, or None on network error.
        response_time_ms: Round-trip time in milliseconds.
        error_message: Details when *status* is not ``healthy``.
    """

    service_name: str
    path: str
    status: str = "unknown"
    status_code: int | None = None
    response_time_ms: float | None = None
    error_message: str = ""


@dataclass(frozen=True)
class EntitlementsCallResult:
    """Outcome of a single ADME Entitlements API call.

    Attributes:
        endpoint: Logical label for the call site (e.g. ``members.self``
            or ``groups``).  Used for UI labelling and in-session history.
        path: API path that was actually called.
        ok: True when the HTTP response was 2xx and the body parsed.
        http_status: HTTP status code returned, or None on transport
            failure (timeout, network error).
        latency_ms: Round-trip time in milliseconds.  Always populated
            so in-session charts never have to handle holes.
        correlation_id: Server-supplied correlation identifier extracted
            from response headers, or None when no recognised header was
            present.
        error_message: Friendly error description when *ok* is False;
            None on success.
        raw_response: Parsed JSON body when available, otherwise the
            response text, otherwise None (transport failure).
        data: Parsed JSON payload — populated only when *ok* is True.
    """

    endpoint: str
    path: str
    ok: bool
    http_status: int | None = None
    latency_ms: float = 0.0
    correlation_id: str | None = None
    error_message: str | None = None
    raw_response: dict | str | None = None
    data: dict | None = None


# Canonical list of OSDU services and their lightweight probe endpoints.
# Each tuple is (display_name, probe_path, http_method).
OSDU_SERVICES: list[tuple[str, str, str]] = [
    ("Storage", "/api/storage/v2/query/kinds?limit=1", "GET"),
    ("Search", "/api/search/v2/query", "POST"),
    ("Schema", "/api/schema-service/v1/schema?limit=1", "GET"),
    ("Legal", "/api/legal/v1/legaltags?valid=true", "GET"),
    ("Entitlements", "/api/entitlements/v2/groups", "GET"),
    ("Workflow", "/api/workflow/v1/workflow", "GET"),
    ("File", "/api/file/v2/getFileList", "GET"),
    ("Dataset", "/api/dataset/v1/getDatasetRegistry", "GET"),
    ("Indexer", "/api/indexer/v2/readiness_check", "GET"),
    ("Notification", "/api/notification/v1/info", "GET"),
    ("EDS", "/api/eds/v1/health/readiness_check", "GET"),
]
