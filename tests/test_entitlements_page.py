"""Tests for the ADME entitlements smoke-test page."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

from app.connection_state import (
    CONNECTION_KEY,
    USER_AUTH_STATE_KEY,
)
from app.models.connection import (
    ADMEConnection,
    AuthMethod,
    EntitlementsCallResult,
)
from app.services.auth import UserAuthState
from tests.support.streamlit_recorder import StreamlitRecorder

ENTITLEMENTS_PAGE_PATH = (
    Path(__file__).resolve().parents[1]
    / "app"
    / "pages"
    / "2_🔑_Entitlements.py"
)

HISTORY_KEY = "entitlements_history"
AUTORUN_KEY = "entitlements_autorun_done"
LAST_MY_GROUPS_KEY = "entitlements_last_my_groups"
LAST_GROUPS_KEY = "entitlements_last_groups"
RERUN_LABEL = "🔄 Re-run entitlements test"
CLEAR_LABEL = "🧹 Clear history"

_OID = "11111111-2222-3333-4444-555555555555"
_MY_GROUPS_LABEL = f"members.{_OID}.groups"


def _load_entitlements_module(
    streamlit_recorder: StreamlitRecorder,
    monkeypatch: pytest.MonkeyPatch,
) -> ModuleType:
    monkeypatch.setitem(sys.modules, "streamlit", streamlit_recorder)
    module_name = "tests.generated_entitlements_page"
    sys.modules.pop(module_name, None)
    spec = importlib.util.spec_from_file_location(
        module_name, ENTITLEMENTS_PAGE_PATH
    )
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _service_principal_connection() -> ADMEConnection:
    return ADMEConnection(
        endpoint="https://example.energy.azure.com",
        tenant_id="11111111-1111-1111-1111-111111111111",
        client_id="22222222-2222-2222-2222-222222222222",
        data_partition_id="example-opendes",
        auth_method=AuthMethod.SERVICE_PRINCIPAL,
        client_secret="placeholder-secret",
    )


def _user_connection() -> ADMEConnection:
    return ADMEConnection(
        endpoint="https://example.energy.azure.com",
        tenant_id="11111111-1111-1111-1111-111111111111",
        client_id="22222222-2222-2222-2222-222222222222",
        data_partition_id="example-opendes",
        auth_method=AuthMethod.USER_IMPERSONATION,
    )


def _ok_my_groups_result(
    *,
    des_id: str = "operator@example.com",
    member_email: str = "operator@example.com",
    groups: list[dict[str, Any]] | None = None,
) -> EntitlementsCallResult:
    if groups is None:
        groups = [
            {"name": "users", "email": "users@example", "description": "all"},
            {"name": "admins", "email": "admins@example", "description": "ops"},
        ]
    payload: dict[str, Any] = {
        "desId": des_id,
        "memberEmail": member_email,
        "groups": groups,
    }
    return EntitlementsCallResult(
        endpoint=_MY_GROUPS_LABEL,
        path=f"/api/entitlements/v2/members/{_OID}/groups?type=none",
        ok=True,
        http_status=200,
        latency_ms=12.3,
        correlation_id="corr-mygroups",
        error_message=None,
        raw_response=payload,
        data=payload,
    )


def _ok_groups_result() -> EntitlementsCallResult:
    payload = {
        "groups": [
            {"name": "users", "email": "users@example", "description": "all"},
        ]
    }
    return EntitlementsCallResult(
        endpoint="groups",
        path="/api/entitlements/v2/groups",
        ok=True,
        http_status=200,
        latency_ms=22.7,
        correlation_id="corr-groups",
        error_message=None,
        raw_response=payload,
        data=payload,
    )


def _failed_my_groups_result() -> EntitlementsCallResult:
    return EntitlementsCallResult(
        endpoint=_MY_GROUPS_LABEL,
        path=f"/api/entitlements/v2/members/{_OID}/groups?type=none",
        ok=False,
        http_status=403,
        latency_ms=8.1,
        correlation_id="corr-fail-7",
        error_message="forbidden by policy",
        raw_response={"message": "forbidden by policy"},
        data=None,
    )


def _patch_service(
    page_module: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    *,
    my_groups_result: EntitlementsCallResult | None = None,
    groups_result: EntitlementsCallResult | None = None,
    token: str = "test-token",
    object_id: str | None = _OID,
) -> dict[str, list[Any]]:
    """Patch the page's bound service + token + OID symbols and record calls."""
    my_groups_calls: list[tuple[Any, str, str]] = []
    groups_calls: list[tuple[Any, str]] = []
    token_calls: list[Any] = []
    extract_calls: list[str] = []
    extract_first_calls: list[tuple[str, tuple[str, ...]]] = []

    def fake_get_token(connection: ADMEConnection, **_: Any) -> str:
        token_calls.append(connection)
        return token

    def fake_extract_object_id(supplied_token: str) -> str | None:
        extract_calls.append(supplied_token)
        return object_id

    def fake_extract_first_string_claim(
        supplied_token: str,
        claim_names: tuple[str, ...],
    ) -> str | None:
        extract_first_calls.append((supplied_token, tuple(claim_names)))
        return object_id

    def fake_fetch_my_groups(
        connection: ADMEConnection,
        supplied_token: str,
        supplied_object_id: str,
    ) -> EntitlementsCallResult:
        my_groups_calls.append(
            (connection, supplied_token, supplied_object_id)
        )
        return my_groups_result or _ok_my_groups_result()

    def fake_fetch_groups(
        connection: ADMEConnection, supplied_token: str
    ) -> EntitlementsCallResult:
        groups_calls.append((connection, supplied_token))
        return groups_result or _ok_groups_result()

    monkeypatch.setattr(page_module, "get_token", fake_get_token)
    monkeypatch.setattr(
        page_module, "extract_object_id", fake_extract_object_id
    )
    monkeypatch.setattr(
        page_module,
        "extract_first_string_claim",
        fake_extract_first_string_claim,
    )
    monkeypatch.setattr(page_module, "fetch_my_groups", fake_fetch_my_groups)
    monkeypatch.setattr(page_module, "fetch_groups", fake_fetch_groups)

    return {
        "my_groups": my_groups_calls,
        "groups": groups_calls,
        "token": token_calls,
        "extract": extract_calls,
        "extract_first": extract_first_calls,
    }


# ---------------------------------------------------------------------------
# Pre-flight guards
# ---------------------------------------------------------------------------


def test_page_blocks_when_no_connection_configured(
    streamlit_recorder: StreamlitRecorder,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    page_module = _load_entitlements_module(streamlit_recorder, monkeypatch)
    spy = _patch_service(page_module, monkeypatch)

    page_module.main()

    info_messages = [
        call.args[0] for call in streamlit_recorder.calls_named("info")
    ]
    assert any(
        "Settings" in message and "configure" in message.lower()
        for message in info_messages
    )
    assert streamlit_recorder.calls_named("page_link"), (
        "page should link operators back to Settings"
    )
    assert spy["my_groups"] == []
    assert spy["groups"] == []
    assert spy["token"] == []
    assert spy["extract"] == []


def test_page_blocks_when_user_token_missing(
    streamlit_recorder: StreamlitRecorder,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """User-impersonation connection without a token must not call services."""
    streamlit_recorder.session_state[CONNECTION_KEY] = _user_connection()
    streamlit_recorder.session_state[USER_AUTH_STATE_KEY] = None
    page_module = _load_entitlements_module(streamlit_recorder, monkeypatch)
    spy = _patch_service(page_module, monkeypatch)

    page_module.main()

    info_messages = [
        call.args[0] for call in streamlit_recorder.calls_named("info")
    ]
    assert any("Settings" in message for message in info_messages)
    assert spy["my_groups"] == []
    assert spy["groups"] == []
    assert spy["extract"] == []


def test_page_blocks_when_data_partition_missing(
    streamlit_recorder: StreamlitRecorder,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Invalid connection (no data_partition_id) must not run the test."""
    streamlit_recorder.session_state[CONNECTION_KEY] = ADMEConnection(
        endpoint="https://example.energy.azure.com",
        tenant_id="11111111-1111-1111-1111-111111111111",
        client_id="22222222-2222-2222-2222-222222222222",
        data_partition_id="",
        auth_method=AuthMethod.SERVICE_PRINCIPAL,
        client_secret="placeholder-secret",
    )
    page_module = _load_entitlements_module(streamlit_recorder, monkeypatch)
    spy = _patch_service(page_module, monkeypatch)

    page_module.main()

    assert streamlit_recorder.calls_named("page_link"), (
        "operators should be pointed back to Settings"
    )
    assert spy["my_groups"] == []
    assert spy["groups"] == []


# ---------------------------------------------------------------------------
# Pre-flight: token has no OID claim — friendly error, no HTTP fired
# ---------------------------------------------------------------------------


def test_page_blocks_when_user_token_has_no_oid_claim(
    streamlit_recorder: StreamlitRecorder,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    streamlit_recorder.session_state[CONNECTION_KEY] = _user_connection()
    streamlit_recorder.session_state[USER_AUTH_STATE_KEY] = UserAuthState(
        access_token="placeholder-user-token",
    )
    page_module = _load_entitlements_module(streamlit_recorder, monkeypatch)
    spy = _patch_service(page_module, monkeypatch, object_id=None)

    page_module.main()

    # Token was retrieved (so we could try to read the claim) and OID
    # extraction was attempted exactly once.
    assert len(spy["token"]) == 1
    assert spy["extract"] == ["test-token"]
    assert spy["extract_first"] == []

    error_messages = [
        call.args[0] for call in streamlit_recorder.calls_named("error")
    ]
    assert error_messages, "no-OID branch must surface a friendly error"
    combined = "\n".join(error_messages)
    assert "Object ID" in combined
    assert "Settings" in combined or any(
        "Settings" in str(call.args[0])
        for call in streamlit_recorder.calls_named("page_link")
    )

    # Page must link back to Settings so the operator can re-sign-in.
    assert streamlit_recorder.calls_named("page_link"), (
        "no-OID branch must link operators back to Settings"
    )

    # Crucially, neither HTTP call fires.
    assert spy["my_groups"] == []
    assert spy["groups"] == []


# ---------------------------------------------------------------------------
# Auto-run behavior
# ---------------------------------------------------------------------------


def test_auto_run_fires_both_calls_on_first_render(
    streamlit_recorder: StreamlitRecorder,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    streamlit_recorder.session_state[CONNECTION_KEY] = (
        _service_principal_connection()
    )
    page_module = _load_entitlements_module(streamlit_recorder, monkeypatch)
    spy = _patch_service(page_module, monkeypatch)

    page_module.main()

    assert len(spy["token"]) == 1
    assert spy["extract"] == []
    assert spy["extract_first"] == [
        ("test-token", ("appid", "azp", "oid")),
    ]
    assert len(spy["my_groups"]) == 1
    # fetch_my_groups received the member ID extracted from SP token claims.
    assert spy["my_groups"][0][2] == _OID
    assert len(spy["groups"]) == 1
    assert streamlit_recorder.session_state[AUTORUN_KEY] is True


def test_auto_run_does_not_fire_again_on_rerun(
    streamlit_recorder: StreamlitRecorder,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    streamlit_recorder.session_state[CONNECTION_KEY] = (
        _service_principal_connection()
    )
    streamlit_recorder.session_state[AUTORUN_KEY] = True
    streamlit_recorder.session_state[LAST_MY_GROUPS_KEY] = (
        _ok_my_groups_result()
    )
    streamlit_recorder.session_state[LAST_GROUPS_KEY] = _ok_groups_result()
    page_module = _load_entitlements_module(streamlit_recorder, monkeypatch)
    spy = _patch_service(page_module, monkeypatch)

    page_module.main()

    assert spy["my_groups"] == []
    assert spy["groups"] == []
    assert spy["token"] == []
    assert spy["extract"] == []
    assert spy["extract_first"] == []


def test_rerun_button_bypasses_autorun_guard(
    streamlit_recorder: StreamlitRecorder,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    streamlit_recorder.session_state[CONNECTION_KEY] = (
        _service_principal_connection()
    )
    streamlit_recorder.session_state[AUTORUN_KEY] = True
    streamlit_recorder.button_responses[RERUN_LABEL] = True
    page_module = _load_entitlements_module(streamlit_recorder, monkeypatch)
    spy = _patch_service(page_module, monkeypatch)

    page_module.main()

    # Both calls fire when the operator hits Re-run, even though autorun is True.
    assert len(spy["my_groups"]) == 1
    assert len(spy["groups"]) == 1


def test_service_principal_member_id_falls_back_to_client_id_when_claim_missing(
    streamlit_recorder: StreamlitRecorder,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    connection = _service_principal_connection()
    streamlit_recorder.session_state[CONNECTION_KEY] = connection
    page_module = _load_entitlements_module(streamlit_recorder, monkeypatch)
    spy = _patch_service(page_module, monkeypatch, object_id=None)

    page_module.main()

    assert len(spy["my_groups"]) == 1
    assert spy["my_groups"][0][2] == connection.client_id
    assert spy["extract"] == []
    assert spy["extract_first"] == [
        ("test-token", ("appid", "azp", "oid")),
    ]


# ---------------------------------------------------------------------------
# Identity card + my-groups card rendering
# ---------------------------------------------------------------------------


def test_identity_card_renders_des_id_and_member_email(
    streamlit_recorder: StreamlitRecorder,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    streamlit_recorder.session_state[CONNECTION_KEY] = (
        _service_principal_connection()
    )
    page_module = _load_entitlements_module(streamlit_recorder, monkeypatch)
    _patch_service(
        page_module,
        monkeypatch,
        my_groups_result=_ok_my_groups_result(
            des_id="alice@example.com",
            member_email="alice.user@example.com",
        ),
    )

    page_module.main()

    success_messages = [
        call.args[0] for call in streamlit_recorder.calls_named("success")
    ]
    combined = "\n".join(success_messages)
    assert "alice@example.com" in combined
    assert "alice.user@example.com" in combined


def test_my_groups_subheader_shows_count_from_response(
    streamlit_recorder: StreamlitRecorder,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    streamlit_recorder.session_state[CONNECTION_KEY] = (
        _service_principal_connection()
    )
    page_module = _load_entitlements_module(streamlit_recorder, monkeypatch)
    _patch_service(
        page_module,
        monkeypatch,
        my_groups_result=_ok_my_groups_result(
            groups=[
                {"name": "g1", "email": "g1@x", "description": ""},
                {"name": "g2", "email": "g2@x", "description": ""},
                {"name": "g3", "email": "g3@x", "description": ""},
            ],
        ),
    )

    page_module.main()

    subheaders = [
        call.args[0] for call in streamlit_recorder.calls_named("subheader")
    ]
    assert any(
        "Groups you belong to" in s and "(3)" in s for s in subheaders
    ), f"missing 'Groups you belong to (3)' subheader; got {subheaders!r}"


def test_empty_my_groups_shows_friendly_admin_message(
    streamlit_recorder: StreamlitRecorder,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    streamlit_recorder.session_state[CONNECTION_KEY] = (
        _service_principal_connection()
    )
    page_module = _load_entitlements_module(streamlit_recorder, monkeypatch)
    _patch_service(
        page_module,
        monkeypatch,
        my_groups_result=_ok_my_groups_result(groups=[]),
    )

    page_module.main()

    info_messages = [
        call.args[0] for call in streamlit_recorder.calls_named("info")
    ]
    combined = "\n".join(info_messages)
    assert "ask an admin" in combined.lower()


# ---------------------------------------------------------------------------
# Caller-accessible groups expander
# ---------------------------------------------------------------------------


def test_all_groups_expander_exists_collapsed_and_does_not_block_groups_call(
    streamlit_recorder: StreamlitRecorder,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    streamlit_recorder.session_state[CONNECTION_KEY] = (
        _service_principal_connection()
    )
    page_module = _load_entitlements_module(streamlit_recorder, monkeypatch)
    spy = _patch_service(page_module, monkeypatch)

    page_module.main()

    expanders = streamlit_recorder.calls_named("expander")
    accessible_groups_expanders = [
        call for call in expanders
        if call.args and "Groups accessible to this token" in call.args[0]
    ]
    assert len(accessible_groups_expanders) == 1, (
        "caller-accessible groups expander should be rendered exactly once"
    )
    assert accessible_groups_expanders[0].kwargs.get("expanded") is False, (
        "caller-accessible groups expander must default to collapsed"
    )

    # Collapsing the expander does NOT prevent fetch_groups from running —
    # the call still fires so the latency chart and history have data.
    assert len(spy["groups"]) == 1
    success_messages = [
        call.args[0] for call in streamlit_recorder.calls_named("success")
    ]
    assert any("accessible to this token" in message for message in success_messages)


# ---------------------------------------------------------------------------
# History append: 2 entries with the new endpoint labels
# ---------------------------------------------------------------------------


def test_each_run_appends_two_history_entries_with_correct_labels(
    streamlit_recorder: StreamlitRecorder,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    streamlit_recorder.session_state[CONNECTION_KEY] = (
        _service_principal_connection()
    )
    page_module = _load_entitlements_module(streamlit_recorder, monkeypatch)
    _patch_service(page_module, monkeypatch)

    page_module.main()

    history = streamlit_recorder.session_state[HISTORY_KEY]
    assert isinstance(history, list)
    assert len(history) == 2
    endpoints = [entry["endpoint"] for entry in history]
    assert endpoints == [_MY_GROUPS_LABEL, "groups"]
    assert all("timestamp" in entry for entry in history)
    assert all("latency_ms" in entry for entry in history)
    assert all("ok" in entry for entry in history)


def test_clear_history_button_empties_session_history(
    streamlit_recorder: StreamlitRecorder,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    streamlit_recorder.session_state[CONNECTION_KEY] = (
        _service_principal_connection()
    )
    streamlit_recorder.session_state[AUTORUN_KEY] = True
    streamlit_recorder.session_state[HISTORY_KEY] = [
        {
            "timestamp": "2026-05-06T10:30:00Z",
            "endpoint": _MY_GROUPS_LABEL,
            "latency_ms": 10.0,
            "http_status": 200,
            "ok": True,
        },
        {
            "timestamp": "2026-05-06T10:30:01Z",
            "endpoint": "groups",
            "latency_ms": 12.0,
            "http_status": 200,
            "ok": True,
        },
    ]
    streamlit_recorder.session_state[LAST_MY_GROUPS_KEY] = (
        _ok_my_groups_result()
    )
    streamlit_recorder.session_state[LAST_GROUPS_KEY] = _ok_groups_result()
    streamlit_recorder.button_responses[CLEAR_LABEL] = True
    page_module = _load_entitlements_module(streamlit_recorder, monkeypatch)
    spy = _patch_service(page_module, monkeypatch)

    page_module.main()

    assert streamlit_recorder.session_state[HISTORY_KEY] == []
    assert streamlit_recorder.session_state[LAST_MY_GROUPS_KEY] is None
    assert streamlit_recorder.session_state[LAST_GROUPS_KEY] is None
    assert streamlit_recorder.session_state[AUTORUN_KEY] is True
    assert streamlit_recorder.calls_named("rerun")
    assert spy["my_groups"] == []
    assert spy["groups"] == []


# ---------------------------------------------------------------------------
# Error rendering on my-groups failure
# ---------------------------------------------------------------------------


def test_failed_my_groups_surfaces_message_status_and_correlation_id(
    streamlit_recorder: StreamlitRecorder,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    streamlit_recorder.session_state[CONNECTION_KEY] = (
        _service_principal_connection()
    )
    page_module = _load_entitlements_module(streamlit_recorder, monkeypatch)
    _patch_service(
        page_module,
        monkeypatch,
        my_groups_result=_failed_my_groups_result(),
    )

    page_module.main()

    error_messages = [
        call.args[0] for call in streamlit_recorder.calls_named("error")
    ]
    assert error_messages, "expected at least one st.error for failed my-groups"
    combined = "\n".join(error_messages)
    assert "forbidden by policy" in combined
    assert "HTTP 403" in combined
    assert "corr-fail-7" in combined

    # Identity success card MUST NOT render the desId / memberEmail block on
    # failure — only the all-groups success card from the still-ok fetch_groups
    # call may surface a success message. Confirm no success contains the
    # identity copy.
    success_messages = [
        call.args[0] for call in streamlit_recorder.calls_named("success")
    ]
    assert not any(
        "Authenticated as" in str(message) for message in success_messages
    ), (
        "identity success card must not render when fetch_my_groups failed"
    )


# ---------------------------------------------------------------------------
# User-impersonation flow with stored auth state runs the test
# ---------------------------------------------------------------------------


def test_user_impersonation_with_token_runs_test(
    streamlit_recorder: StreamlitRecorder,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    streamlit_recorder.session_state[CONNECTION_KEY] = _user_connection()
    streamlit_recorder.session_state[USER_AUTH_STATE_KEY] = UserAuthState(
        access_token="placeholder-user-token",
    )
    page_module = _load_entitlements_module(streamlit_recorder, monkeypatch)
    spy = _patch_service(page_module, monkeypatch)

    page_module.main()

    assert len(spy["my_groups"]) == 1
    assert len(spy["groups"]) == 1
    assert spy["extract"] == ["test-token"]
    assert spy["extract_first"] == []
