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
LAST_MEMBER_KEY = "entitlements_last_member"
LAST_GROUPS_KEY = "entitlements_last_groups"
RERUN_LABEL = "🔄 Re-run entitlements test"
CLEAR_LABEL = "🧹 Clear history"


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


def _ok_member_result() -> EntitlementsCallResult:
    return EntitlementsCallResult(
        endpoint="members.self",
        path="/api/entitlements/v2/members/me",
        ok=True,
        http_status=200,
        latency_ms=12.3,
        correlation_id="corr-self",
        error_message=None,
        raw_response={"email": "op@example.com"},
        data={"email": "op@example.com"},
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


def _failed_result() -> EntitlementsCallResult:
    return EntitlementsCallResult(
        endpoint="groups",
        path="/api/entitlements/v2/groups",
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
    member_result: EntitlementsCallResult | None = None,
    groups_result: EntitlementsCallResult | None = None,
    token: str = "test-token",
) -> dict[str, list[Any]]:
    """Patch the page's bound service + token symbols and record calls."""
    member_calls: list[tuple[Any, str]] = []
    groups_calls: list[tuple[Any, str]] = []
    token_calls: list[Any] = []

    def fake_get_token(connection: ADMEConnection, **_: Any) -> str:
        token_calls.append(connection)
        return token

    def fake_fetch_member_self(
        connection: ADMEConnection, supplied_token: str
    ) -> EntitlementsCallResult:
        member_calls.append((connection, supplied_token))
        return member_result or _ok_member_result()

    def fake_fetch_groups(
        connection: ADMEConnection, supplied_token: str
    ) -> EntitlementsCallResult:
        groups_calls.append((connection, supplied_token))
        return groups_result or _ok_groups_result()

    monkeypatch.setattr(page_module, "get_token", fake_get_token)
    monkeypatch.setattr(page_module, "fetch_member_self", fake_fetch_member_self)
    monkeypatch.setattr(page_module, "fetch_groups", fake_fetch_groups)

    return {
        "member": member_calls,
        "groups": groups_calls,
        "token": token_calls,
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
    assert spy["member"] == []
    assert spy["groups"] == []
    assert spy["token"] == []


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
    assert spy["member"] == []
    assert spy["groups"] == []


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
    assert spy["member"] == []
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

    assert len(spy["member"]) == 1
    assert len(spy["groups"]) == 1
    assert len(spy["token"]) == 1
    assert streamlit_recorder.session_state[AUTORUN_KEY] is True


def test_auto_run_does_not_fire_again_on_rerun(
    streamlit_recorder: StreamlitRecorder,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    streamlit_recorder.session_state[CONNECTION_KEY] = (
        _service_principal_connection()
    )
    streamlit_recorder.session_state[AUTORUN_KEY] = True
    streamlit_recorder.session_state[LAST_MEMBER_KEY] = _ok_member_result()
    streamlit_recorder.session_state[LAST_GROUPS_KEY] = _ok_groups_result()
    page_module = _load_entitlements_module(streamlit_recorder, monkeypatch)
    spy = _patch_service(page_module, monkeypatch)

    page_module.main()

    assert spy["member"] == []
    assert spy["groups"] == []
    assert spy["token"] == []


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

    assert len(spy["member"]) == 1
    assert len(spy["groups"]) == 1


# ---------------------------------------------------------------------------
# History append + clear
# ---------------------------------------------------------------------------


def test_each_run_appends_two_history_entries(
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
    assert endpoints == ["members.self", "groups"]
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
            "timestamp": "2026-05-05T10:30:00Z",
            "endpoint": "members.self",
            "latency_ms": 10.0,
            "http_status": 200,
            "ok": True,
        },
        {
            "timestamp": "2026-05-05T10:30:01Z",
            "endpoint": "groups",
            "latency_ms": 12.0,
            "http_status": 200,
            "ok": True,
        },
    ]
    streamlit_recorder.session_state[LAST_MEMBER_KEY] = _ok_member_result()
    streamlit_recorder.session_state[LAST_GROUPS_KEY] = _ok_groups_result()
    streamlit_recorder.button_responses[CLEAR_LABEL] = True
    page_module = _load_entitlements_module(streamlit_recorder, monkeypatch)
    _patch_service(page_module, monkeypatch)

    page_module.main()

    assert streamlit_recorder.session_state[HISTORY_KEY] == []
    assert streamlit_recorder.session_state[LAST_MEMBER_KEY] is None
    assert streamlit_recorder.session_state[LAST_GROUPS_KEY] is None


# ---------------------------------------------------------------------------
# Error rendering
# ---------------------------------------------------------------------------


def test_failed_call_surfaces_message_status_and_correlation_id(
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
        groups_result=_failed_result(),
    )

    page_module.main()

    error_messages = [
        call.args[0] for call in streamlit_recorder.calls_named("error")
    ]
    assert error_messages, "expected at least one st.error for the failed call"
    combined = "\n".join(error_messages)
    assert "forbidden by policy" in combined
    assert "HTTP 403" in combined
    assert "corr-fail-7" in combined


# ---------------------------------------------------------------------------
# User-impersonation flow with a stored auth state runs the test
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

    assert len(spy["member"]) == 1
    assert len(spy["groups"]) == 1
