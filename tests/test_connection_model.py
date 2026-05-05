"""Tests for ADME connection validation contracts."""

from __future__ import annotations

import pytest

from app.models.connection import (
    ADME_RESOURCE_SCOPE,
    OSDU_SERVICES,
    ADMEConnection,
    AuthMethod,
)


def _build_connection(
    *,
    endpoint: str = "https://example.energy.azure.com",
    tenant_id: str = "11111111-1111-1111-1111-111111111111",
    client_id: str = "22222222-2222-2222-2222-222222222222",
    data_partition_id: str = "example-opendes",
    auth_method: AuthMethod = AuthMethod.USER_IMPERSONATION,
    client_secret: str = "",
    token_scope: str | None = None,
) -> ADMEConnection:
    if token_scope is None:
        return ADMEConnection(
            endpoint=endpoint,
            tenant_id=tenant_id,
            client_id=client_id,
            data_partition_id=data_partition_id,
            auth_method=auth_method,
            client_secret=client_secret,
        )
    return ADMEConnection(
        endpoint=endpoint,
        tenant_id=tenant_id,
        client_id=client_id,
        data_partition_id=data_partition_id,
        token_scope=token_scope,
        auth_method=auth_method,
        client_secret=client_secret,
    )


def test_supported_auth_methods_match_issue_contract() -> None:
    assert {method.value for method in AuthMethod} == {
        "user_impersonation",
        "service_principal",
    }


@pytest.mark.parametrize(
    "connection",
    [
        pytest.param(_build_connection(endpoint=""), id="missing-endpoint"),
        pytest.param(_build_connection(tenant_id=""), id="missing-tenant-id"),
        pytest.param(_build_connection(client_id=""), id="missing-client-id"),
        pytest.param(
            _build_connection(data_partition_id=""),
            id="missing-data-partition-id",
        ),
    ],
)
def test_connection_is_invalid_when_issue_required_field_is_missing(
    connection: ADMEConnection,
) -> None:
    assert not connection.is_valid()


def test_user_impersonation_does_not_require_client_secret() -> None:
    assert _build_connection(auth_method=AuthMethod.USER_IMPERSONATION).is_valid()


def test_service_principal_requires_client_secret() -> None:
    assert not _build_connection(auth_method=AuthMethod.SERVICE_PRINCIPAL).is_valid()


def test_service_principal_accepts_client_secret() -> None:
    assert _build_connection(
        auth_method=AuthMethod.SERVICE_PRINCIPAL,
        client_secret="test-client-secret",
    ).is_valid()


@pytest.mark.parametrize(
    "client_id",
    [
        pytest.param("22222222-2222-2222-2222-222222222222", id="uuid"),
        pytest.param("custom-app-registration-id", id="custom-app"),
    ],
)
def test_connection_scope_uses_shared_adme_resource_scope(client_id: str) -> None:
    connection = _build_connection(client_id=client_id)

    assert connection.token_scope == ADME_RESOURCE_SCOPE
    assert connection.scope == ADME_RESOURCE_SCOPE


def test_connection_scope_uses_custom_token_scope() -> None:
    connection = _build_connection(token_scope="https://custom.example/.default")

    assert connection.scope == "https://custom.example/.default"


def test_connection_scope_trims_custom_token_scope() -> None:
    connection = _build_connection(token_scope="  https://custom.example/.default  ")

    assert connection.scope == "https://custom.example/.default"


@pytest.mark.parametrize(
    "token_scope",
    [
        pytest.param("", id="empty"),
        pytest.param("   ", id="whitespace"),
    ],
)
def test_connection_scope_falls_back_to_default_when_token_scope_is_blank(
    token_scope: str,
) -> None:
    connection = _build_connection(token_scope=token_scope)

    assert connection.scope == ADME_RESOURCE_SCOPE
    assert connection.is_valid()


def test_connection_validation_does_not_reject_custom_token_scope_format() -> None:
    connection = _build_connection(token_scope="operator supplied custom scope")

    assert connection.is_valid()


def test_osdu_services_include_eds_probe() -> None:
    assert ("EDS", "/api/eds/v1/health/readiness_check", "GET") in OSDU_SERVICES


def test_osdu_services_use_indexer_readiness_probe() -> None:
    assert ("Indexer", "/api/indexer/v2/readiness_check", "GET") in OSDU_SERVICES
