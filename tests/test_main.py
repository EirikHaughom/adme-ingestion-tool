"""Tests for the main Streamlit entry point."""

from __future__ import annotations

import importlib
import sys
from types import ModuleType

import pytest

from app.connection_state import CONNECTION_KEY, HEALTH_ERROR_KEY, HEALTH_RESULTS_KEY
from app.models.connection import ADMEConnection, AuthMethod, ServiceHealthResult
from app.storage_bridge import StorageSyncStatus
from tests.support.streamlit_recorder import StreamlitRecorder


def _load_main_module(
    streamlit_recorder: StreamlitRecorder,
    monkeypatch: pytest.MonkeyPatch,
) -> ModuleType:
    monkeypatch.setitem(sys.modules, "streamlit", streamlit_recorder)
    sys.modules.pop("app.main", None)
    module = importlib.import_module("app.main")
    monkeypatch.setattr(
        module,
        "load_persisted_connection_state",
        lambda session_state: StorageSyncStatus(available=True),
    )
    return module


def test_main_sets_expected_page_config(
    streamlit_recorder: StreamlitRecorder,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    main_module = _load_main_module(streamlit_recorder, monkeypatch)

    main_module.main()

    [page_config_call] = streamlit_recorder.calls_named("set_page_config")
    assert page_config_call.kwargs == {
        "page_title": "ADME Control Plane",
        "page_icon": "⚡",
        "layout": "wide",
    }


def test_main_renders_expected_title(
    streamlit_recorder: StreamlitRecorder,
    monkeypatch: pytest.MonkeyPatch,
    app_title: str,
) -> None:
    main_module = _load_main_module(streamlit_recorder, monkeypatch)

    main_module.main()

    [title_call] = streamlit_recorder.calls_named("title")
    assert title_call.args == (app_title,)


def test_main_prompts_operator_to_open_settings_when_not_configured(
    streamlit_recorder: StreamlitRecorder,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    main_module = _load_main_module(streamlit_recorder, monkeypatch)

    main_module.main()

    warning_messages = [
        call.args[0] for call in streamlit_recorder.calls_named("warning")
    ]
    assert (
        "No ADME connection is configured for this session."
    ) in warning_messages

    [page_link_call] = streamlit_recorder.calls_named("page_link")
    assert page_link_call.args == ("pages/1_⚙️_Settings.py",)
    assert page_link_call.kwargs == {
        "label": "Open Settings",
        "icon": "⚙️",
    }

    [markdown_call] = [
        call
        for call in streamlit_recorder.calls_named("markdown")
        if call.args == ("**Status:** Not configured",)
    ]
    assert markdown_call.args == ("**Status:** Not configured",)


def test_main_loads_saved_profile_and_validation_from_storage(
    streamlit_recorder: StreamlitRecorder,
    monkeypatch: pytest.MonkeyPatch,
    healthy_service_results: list[ServiceHealthResult],
) -> None:
    main_module = _load_main_module(streamlit_recorder, monkeypatch)

    def fake_load_persisted_connection_state(
        session_state: dict[str, object],
    ) -> StorageSyncStatus:
        session_state[CONNECTION_KEY] = ADMEConnection(
            endpoint="https://stored.energy.azure.com",
            tenant_id="11111111-1111-1111-1111-111111111111",
            client_id="22222222-2222-2222-2222-222222222222",
            data_partition_id="stored-opendes",
            auth_method=AuthMethod.USER_IMPERSONATION,
        )
        session_state[HEALTH_RESULTS_KEY] = healthy_service_results
        return StorageSyncStatus(
            available=True,
            message="Loaded saved connection settings and latest validation.",
            severity="info",
            profile_loaded=True,
            health_loaded=True,
        )

    monkeypatch.setattr(
        main_module,
        "load_persisted_connection_state",
        fake_load_persisted_connection_state,
    )

    main_module.main()

    assert any(
        call.args
        == (
            "Loaded saved connection settings and latest validation.",
        )
        for call in streamlit_recorder.calls_named("info")
    )
    assert any(
        "https://stored.energy.azure.com" in call.args[0]
        for call in streamlit_recorder.calls_named("markdown")
    )
    [success_call] = streamlit_recorder.calls_named("success")
    assert success_call.args == (
        "All 11 configured OSDU services responded successfully.",
    )


def test_main_renders_healthy_connection_summary(
    streamlit_recorder: StreamlitRecorder,
    monkeypatch: pytest.MonkeyPatch,
    healthy_service_results: list[ServiceHealthResult],
) -> None:
    streamlit_recorder.session_state[CONNECTION_KEY] = ADMEConnection(
        endpoint="https://example.energy.azure.com",
        tenant_id="11111111-1111-1111-1111-111111111111",
        client_id="22222222-2222-2222-2222-222222222222",
        data_partition_id="example-opendes",
        auth_method=AuthMethod.USER_IMPERSONATION,
    )
    streamlit_recorder.session_state[HEALTH_RESULTS_KEY] = healthy_service_results
    main_module = _load_main_module(streamlit_recorder, monkeypatch)

    main_module.main()

    [success_call] = streamlit_recorder.calls_named("success")
    assert success_call.args == (
        "All 11 configured OSDU services responded successfully.",
    )

    [dataframe_call] = streamlit_recorder.calls_named("dataframe")
    rows = dataframe_call.args[0]
    assert len(rows) == 11
    assert rows[0]["Service"] == "Storage"
    assert rows[-1]["Service"] == "EDS"


def test_main_surfaces_last_health_error(
    streamlit_recorder: StreamlitRecorder,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    streamlit_recorder.session_state[CONNECTION_KEY] = ADMEConnection(
        endpoint="https://example.energy.azure.com",
        tenant_id="11111111-1111-1111-1111-111111111111",
        client_id="22222222-2222-2222-2222-222222222222",
        data_partition_id="example-opendes",
    )
    streamlit_recorder.session_state[HEALTH_ERROR_KEY] = "Authentication failed."
    main_module = _load_main_module(streamlit_recorder, monkeypatch)

    main_module.main()

    [error_call] = streamlit_recorder.calls_named("error")
    assert error_call.args == (
        "Last connection test failed: Authentication failed.",
    )


def test_main_shows_pending_validation_state_for_saved_connection(
    streamlit_recorder: StreamlitRecorder,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    streamlit_recorder.session_state[CONNECTION_KEY] = ADMEConnection(
        endpoint="https://example.energy.azure.com",
        tenant_id="11111111-1111-1111-1111-111111111111",
        client_id="22222222-2222-2222-2222-222222222222",
        data_partition_id="example-opendes",
    )
    main_module = _load_main_module(streamlit_recorder, monkeypatch)

    main_module.main()

    assert any(
        call.args == ("**Status:** Configured · Validation pending",)
        for call in streamlit_recorder.calls_named("markdown")
    )
