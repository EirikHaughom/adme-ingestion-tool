"""Tests for session-scoped ADME connection state helpers."""

from __future__ import annotations

from app.connection_state import (
    CONNECTION_KEY,
    HEALTH_ERROR_KEY,
    HEALTH_RESULTS_KEY,
    USER_AUTH_FLOW_KEY,
    USER_AUTH_STATE_KEY,
    clear_pending_user_auth_flow,
    clear_user_auth_state,
    ensure_session_defaults,
    format_auth_method,
    get_overall_state,
    get_pending_user_auth_flow,
    get_user_auth_state,
    results_to_table_rows,
    save_connection,
    store_pending_user_auth_flow,
    store_user_auth_state,
    summarize_health,
)
from app.models.connection import ADMEConnection, AuthMethod, ServiceHealthResult
from app.services.auth import UserAuthFlowStart, UserAuthState


def test_get_overall_state_requires_a_valid_connection() -> None:
    session_state: dict[str, object] = {}
    assert get_overall_state(session_state) == "not_configured"

    session_state[CONNECTION_KEY] = ADMEConnection(
        endpoint="",
        tenant_id="11111111-1111-1111-1111-111111111111",
        client_id="22222222-2222-2222-2222-222222222222",
        data_partition_id="example-opendes",
    )
    assert get_overall_state(session_state) == "not_configured"


def test_ensure_session_defaults_initializes_user_auth_keys() -> None:
    session_state: dict[str, object] = {}

    ensure_session_defaults(session_state)

    assert session_state[USER_AUTH_FLOW_KEY] is None
    assert session_state[USER_AUTH_STATE_KEY] is None


def test_get_overall_state_prioritizes_latest_error() -> None:
    session_state: dict[str, object] = {
        CONNECTION_KEY: ADMEConnection(
            endpoint="https://example.energy.azure.com",
            tenant_id="11111111-1111-1111-1111-111111111111",
            client_id="22222222-2222-2222-2222-222222222222",
            data_partition_id="example-opendes",
        ),
        HEALTH_RESULTS_KEY: [
            ServiceHealthResult(
                service_name="Storage",
                path="/api/storage/v2/query/kinds?limit=1",
                status="healthy",
                status_code=200,
                response_time_ms=15.0,
            )
        ],
        HEALTH_ERROR_KEY: "Timed out.",
    }

    assert get_overall_state(session_state) == "error"


def test_store_and_clear_pending_user_auth_flow() -> None:
    session_state: dict[str, object] = {}
    flow_start = UserAuthFlowStart(
        authorization_url="https://login.example.test/authorize",
        flow={"state": "placeholder-state"},
    )

    store_pending_user_auth_flow(session_state, flow_start)
    assert get_pending_user_auth_flow(session_state) == flow_start

    clear_pending_user_auth_flow(session_state)
    assert get_pending_user_auth_flow(session_state) is None


def test_store_user_auth_state_clears_stale_health() -> None:
    session_state: dict[str, object] = {
        HEALTH_RESULTS_KEY: [
            ServiceHealthResult(
                service_name="Storage",
                path="/storage",
                status="healthy",
                status_code=200,
            )
        ],
        HEALTH_ERROR_KEY: "Old validation error.",
    }
    auth_state = UserAuthState(access_token="placeholder-user-token")

    store_user_auth_state(session_state, auth_state)

    assert get_user_auth_state(session_state) == auth_state
    assert session_state[HEALTH_RESULTS_KEY] == []
    assert session_state[HEALTH_ERROR_KEY] == ""


def test_clear_user_auth_state_clears_pending_flow_and_health() -> None:
    session_state: dict[str, object] = {
        USER_AUTH_FLOW_KEY: UserAuthFlowStart(
            authorization_url="https://login.example.test/authorize",
            flow={"state": "placeholder-state"},
        ),
        USER_AUTH_STATE_KEY: UserAuthState(access_token="placeholder-user-token"),
        HEALTH_RESULTS_KEY: [
            ServiceHealthResult(
                service_name="Storage",
                path="/storage",
                status="healthy",
                status_code=200,
            )
        ],
        HEALTH_ERROR_KEY: "",
    }

    clear_user_auth_state(session_state)

    assert session_state[USER_AUTH_FLOW_KEY] is None
    assert session_state[USER_AUTH_STATE_KEY] is None
    assert session_state[HEALTH_RESULTS_KEY] == []
    assert session_state[HEALTH_ERROR_KEY] == ""


def test_save_connection_clears_user_auth_when_connection_changes() -> None:
    session_state: dict[str, object] = {
        CONNECTION_KEY: ADMEConnection(
            endpoint="https://old.energy.azure.com",
            tenant_id="11111111-1111-1111-1111-111111111111",
            client_id="22222222-2222-2222-2222-222222222222",
            data_partition_id="old-opendes",
        ),
        USER_AUTH_STATE_KEY: UserAuthState(access_token="placeholder-user-token"),
        HEALTH_RESULTS_KEY: [
            ServiceHealthResult(
                service_name="Storage",
                path="/storage",
                status="healthy",
                status_code=200,
            )
        ],
        HEALTH_ERROR_KEY: "",
    }

    new_connection = ADMEConnection(
        endpoint="https://new.energy.azure.com",
        tenant_id="11111111-1111-1111-1111-111111111111",
        client_id="22222222-2222-2222-2222-222222222222",
        data_partition_id="new-opendes",
    )
    save_connection(session_state, new_connection)

    assert session_state[CONNECTION_KEY] == new_connection
    assert session_state[USER_AUTH_STATE_KEY] is None
    assert session_state[HEALTH_RESULTS_KEY] == []


def test_save_connection_clears_user_auth_when_token_scope_changes() -> None:
    session_state: dict[str, object] = {
        CONNECTION_KEY: ADMEConnection(
            endpoint="https://example.energy.azure.com",
            tenant_id="11111111-1111-1111-1111-111111111111",
            client_id="22222222-2222-2222-2222-222222222222",
            data_partition_id="example-opendes",
            token_scope="https://old.energy.azure.com/.default",
        ),
        USER_AUTH_FLOW_KEY: UserAuthFlowStart(
            authorization_url="https://login.example.test/authorize",
            flow={"state": "placeholder-state"},
        ),
        USER_AUTH_STATE_KEY: UserAuthState(access_token="placeholder-user-token"),
        HEALTH_RESULTS_KEY: [
            ServiceHealthResult(
                service_name="Storage",
                path="/storage",
                status="healthy",
                status_code=200,
            )
        ],
        HEALTH_ERROR_KEY: "Old validation error.",
    }

    new_connection = ADMEConnection(
        endpoint="https://example.energy.azure.com",
        tenant_id="11111111-1111-1111-1111-111111111111",
        client_id="22222222-2222-2222-2222-222222222222",
        data_partition_id="example-opendes",
        token_scope="https://new.energy.azure.com/.default",
    )
    save_connection(session_state, new_connection)

    assert session_state[CONNECTION_KEY] == new_connection
    assert session_state[USER_AUTH_FLOW_KEY] is None
    assert session_state[USER_AUTH_STATE_KEY] is None
    assert session_state[HEALTH_RESULTS_KEY] == []
    assert session_state[HEALTH_ERROR_KEY] == ""


def test_summarize_health_counts_each_state() -> None:
    results = [
        ServiceHealthResult(
            service_name="Storage",
            path="/storage",
            status="healthy",
            status_code=200,
            response_time_ms=12.0,
        ),
        ServiceHealthResult(
            service_name="Search",
            path="/search",
            status="unhealthy",
            status_code=403,
            response_time_ms=18.0,
            error_message="Forbidden",
        ),
        ServiceHealthResult(
            service_name="Workflow",
            path="/workflow",
            status="error",
            response_time_ms=5000.0,
            error_message="Timed out",
        ),
    ]

    summary = summarize_health(results)
    assert summary.total_services == 3
    assert summary.healthy_services == 1
    assert summary.unhealthy_services == 1
    assert summary.error_services == 1
    assert summary.overall_state == "error"


def test_results_to_table_rows_are_operator_friendly() -> None:
    rows = results_to_table_rows(
        [
            ServiceHealthResult(
                service_name="EDS",
                path="/api/eds/v1/retrievalInstructions",
                status="unhealthy",
                status_code=500,
                response_time_ms=11.234,
                error_message="Internal error",
            )
        ]
    )

    assert rows == [
        {
            "Service": "EDS",
            "State": "⚠️ Unhealthy",
            "HTTP": 500,
            "Latency (ms)": 11.2,
            "Detail": "Internal error",
        }
    ]
    assert format_auth_method(AuthMethod.SERVICE_PRINCIPAL) == "Service principal"
