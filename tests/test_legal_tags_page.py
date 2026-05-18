"""Tests for the ADME Legal Tags page (`app/pages/3_🏷️_Legal_Tags.py`)."""

from __future__ import annotations

import importlib.util
import sys
from datetime import date
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

from app.connection_state import (
    CONNECTION_KEY,
    USER_AUTH_STATE_KEY,
)
from app.models.connection import ADMEConnection, AuthMethod
from app.models.osdu import (
    LegalTag,
    LegalTagDetailResult,
    LegalTagListResult,
    LegalTagOperationResult,
    LegalTagPropertiesResult,
    LegalTagPropertiesSpec,
)
from tests.support.streamlit_recorder import StreamlitRecorder

LEGAL_TAGS_PAGE_PATH = (
    Path(__file__).resolve().parents[1]
    / "app"
    / "pages"
    / "3_🏷️_Legal_Tags.py"
)

# Locked session-state keys.
AUTORUN_KEY = "legal_tags_autorun_done"
LIST_KEY = "legal_tags_list"
SELECTED_NAME_KEY = "legal_tags_selected_name"
SELECTED_DETAIL_KEY = "legal_tags_selected_detail"
EDIT_MODE_KEY = "legal_tags_edit_mode"
PROPERTIES_SPEC_KEY = "legal_tags_properties_spec"
PROPERTIES_FALLBACK_KEY = "legal_tags_properties_fallback"
LAST_ERROR_KEY = "legal_tags_last_error"
HISTORY_KEY = "legal_tags_history"
SHOW_VALID_ONLY_KEY = "legal_tags_show_valid_only"
DELETE_CONFIRM_TEXT_KEY = "legal_tags_delete_confirm_text"

FORM_NAME_KEY = "legal_tags_create_form_name"
FORM_DESCRIPTION_KEY = "legal_tags_create_form_description"
FORM_COUNTRY_KEY = "legal_tags_create_form_country_of_origin"
FORM_CONTRACT_KEY = "legal_tags_create_form_contract_id"
FORM_EXPIRATION_KEY = "legal_tags_create_form_expiration_date"
FORM_ORIGINATOR_KEY = "legal_tags_create_form_originator"
FORM_DATA_TYPE_KEY = "legal_tags_create_form_data_type"
FORM_SECURITY_KEY = "legal_tags_create_form_security"
FORM_PERSONAL_DATA_KEY = "legal_tags_create_form_personal_data"
FORM_EXPORT_KEY = "legal_tags_create_form_export_classification"

EDIT_DESCRIPTION_KEY = "legal_tags_edit_form_description"
EDIT_CONTRACT_KEY = "legal_tags_edit_form_contract_id"
EDIT_EXPIRATION_KEY = "legal_tags_edit_form_expiration_date"

REFRESH_LABEL = "🔄 Refresh"
TOGGLE_LABEL = "Show only valid tags"
EDIT_BUTTON_LABEL = "✏️ Edit"
DELETE_BUTTON_LABEL = "🗑️ Delete"
DELETE_CONFIRM_LABEL = "Confirm delete"
DELETE_CANCEL_LABEL = "Cancel"
SUGGEST_DEFAULTS_LABEL = "🪄 Suggest defaults"
CREATE_BUTTON_LABEL = "✅ Create"
CLEAR_HISTORY_LABEL = "🧹 Clear history"
DISMISS_ERROR_LABEL = "Dismiss error"

SAVE_BUTTON_LABEL = "💾 Save changes"
CANCEL_FORM_LABEL = "Cancel"


# ---------------------------------------------------------------------------
# Module loader
# ---------------------------------------------------------------------------


def _load_page(
    streamlit_recorder: StreamlitRecorder,
    monkeypatch: pytest.MonkeyPatch,
) -> ModuleType:
    monkeypatch.setitem(sys.modules, "streamlit", streamlit_recorder)
    module_name = "tests.generated_legal_tags_page"
    sys.modules.pop(module_name, None)
    spec = importlib.util.spec_from_file_location(
        module_name, LEGAL_TAGS_PAGE_PATH
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


def _sample_tag(name: str = "opendes-public-test") -> LegalTag:
    return LegalTag(
        name=name,
        description="Public test tag",
        properties={
            "countryOfOrigin": ["US"],
            "contractId": "No Contract Related",
            "expirationDate": "2099-12-31",
            "originator": "ADME Operator",
            "dataType": "Public Domain Data",
            "securityClassification": "Public",
            "personalData": "No Personal Data",
            "exportClassification": "EAR99",
        },
        is_valid=True,
    )


def _ok_list_result(tags: list[LegalTag] | None = None) -> LegalTagListResult:
    items = tags if tags is not None else [_sample_tag()]
    return LegalTagListResult(
        items=items,
        ok=True,
        http_status=200,
        latency_ms=15.0,
        correlation_id="corr-list",
    )


def _ok_detail_result(tag: LegalTag | None = None) -> LegalTagDetailResult:
    return LegalTagDetailResult(
        tag=tag or _sample_tag(),
        ok=True,
        http_status=200,
        latency_ms=10.0,
        correlation_id="corr-get",
        raw_response={"name": (tag or _sample_tag()).name},
    )


def _ok_properties_result() -> LegalTagPropertiesResult:
    return LegalTagPropertiesResult(
        spec=LegalTagPropertiesSpec(
            country_of_origin=["US", "CA"],
            data_types=["Public Domain Data", "First Party Data"],
            security_classifications=["Public", "Private", "Confidential"],
            export_classifications=["EAR99", "0A998"],
            personal_data_types=[
                "No Personal Data",
                "Personally Identifiable",
            ],
        ),
        ok=True,
        http_status=200,
        latency_ms=5.0,
        correlation_id="corr-props",
    )


def _failed_properties_404() -> LegalTagPropertiesResult:
    return LegalTagPropertiesResult(
        spec=None,
        ok=False,
        http_status=404,
        latency_ms=4.0,
        correlation_id="corr-props-404",
        error_message="no properties endpoint",
    )


# ---------------------------------------------------------------------------
# Service spy
# ---------------------------------------------------------------------------


class _Spy:
    def __init__(self) -> None:
        self.list_calls: list[tuple[Any, str, bool | None]] = []
        self.get_calls: list[tuple[Any, str, str]] = []
        self.create_calls: list[dict[str, Any]] = []
        self.update_calls: list[dict[str, Any]] = []
        self.delete_calls: list[tuple[Any, str, str]] = []
        self.properties_calls: list[tuple[Any, str]] = []
        self.token_calls: list[Any] = []


def _patch_services(
    page_module: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    *,
    list_result: LegalTagListResult | None = None,
    detail_result: LegalTagDetailResult | None = None,
    create_result: LegalTagDetailResult | None = None,
    update_result: LegalTagDetailResult | None = None,
    delete_result: LegalTagOperationResult | None = None,
    properties_result: LegalTagPropertiesResult | None = None,
    token: str | None = "test-token",
) -> _Spy:
    spy = _Spy()

    def fake_get_token(connection: ADMEConnection, **_: Any) -> str:
        spy.token_calls.append(connection)
        if token is None:
            from app.services.auth import AuthenticationError

            raise AuthenticationError("no token")
        return token

    def fake_list(
        connection: ADMEConnection,
        supplied_token: str,
        *,
        valid: bool | None = None,
    ) -> LegalTagListResult:
        spy.list_calls.append((connection, supplied_token, valid))
        return list_result if list_result is not None else _ok_list_result()

    def fake_get(
        connection: ADMEConnection,
        supplied_token: str,
        name: str,
    ) -> LegalTagDetailResult:
        spy.get_calls.append((connection, supplied_token, name))
        return (
            detail_result
            if detail_result is not None
            else _ok_detail_result(_sample_tag(name))
        )

    def fake_create(
        connection: ADMEConnection,
        supplied_token: str,
        *,
        name: str,
        description: str,
        properties: dict[str, Any],
    ) -> LegalTagDetailResult:
        spy.create_calls.append(
            {
                "connection": connection,
                "token": supplied_token,
                "name": name,
                "description": description,
                "properties": properties,
            }
        )
        return (
            create_result
            if create_result is not None
            else _ok_detail_result(_sample_tag(name))
        )

    def fake_update(
        connection: ADMEConnection,
        supplied_token: str,
        *,
        name: str,
        description: str,
        properties: dict[str, Any],
    ) -> LegalTagDetailResult:
        spy.update_calls.append(
            {
                "connection": connection,
                "token": supplied_token,
                "name": name,
                "description": description,
                "properties": properties,
            }
        )
        return (
            update_result
            if update_result is not None
            else _ok_detail_result(_sample_tag(name))
        )

    def fake_delete(
        connection: ADMEConnection,
        supplied_token: str,
        name: str,
    ) -> LegalTagOperationResult:
        spy.delete_calls.append((connection, supplied_token, name))
        return delete_result or LegalTagOperationResult(
            name=name,
            ok=True,
            http_status=204,
            latency_ms=8.0,
            correlation_id="corr-del",
        )

    def fake_properties(
        connection: ADMEConnection, supplied_token: str
    ) -> LegalTagPropertiesResult:
        spy.properties_calls.append((connection, supplied_token))
        return (
            properties_result
            if properties_result is not None
            else _ok_properties_result()
        )

    monkeypatch.setattr(page_module, "get_token", fake_get_token)
    monkeypatch.setattr(page_module, "list_legal_tags", fake_list)
    monkeypatch.setattr(page_module, "get_legal_tag", fake_get)
    monkeypatch.setattr(page_module, "create_legal_tag", fake_create)
    monkeypatch.setattr(page_module, "update_legal_tag", fake_update)
    monkeypatch.setattr(page_module, "delete_legal_tag", fake_delete)
    monkeypatch.setattr(
        page_module, "get_legal_tag_properties", fake_properties
    )
    return spy


# ===========================================================================
# Pre-flight
# ===========================================================================


def test_page_blocks_when_no_connection_configured(
    streamlit_recorder: StreamlitRecorder,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    page_module = _load_page(streamlit_recorder, monkeypatch)
    spy = _patch_services(page_module, monkeypatch)

    page_module.main()

    info_messages = [
        call.args[0] for call in streamlit_recorder.calls_named("info")
    ]
    assert any("Instance Configuration" in m for m in info_messages)
    assert streamlit_recorder.calls_named("page_link")
    assert spy.list_calls == []
    assert spy.properties_calls == []
    assert spy.token_calls == []


def test_page_blocks_user_impersonation_without_token(
    streamlit_recorder: StreamlitRecorder,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    streamlit_recorder.session_state[CONNECTION_KEY] = _user_connection()
    streamlit_recorder.session_state[USER_AUTH_STATE_KEY] = None
    page_module = _load_page(streamlit_recorder, monkeypatch)
    spy = _patch_services(page_module, monkeypatch)

    page_module.main()

    assert streamlit_recorder.calls_named("page_link")
    assert spy.list_calls == []
    assert spy.properties_calls == []


def test_page_blocks_when_data_partition_missing(
    streamlit_recorder: StreamlitRecorder,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    streamlit_recorder.session_state[CONNECTION_KEY] = ADMEConnection(
        endpoint="https://example.energy.azure.com",
        tenant_id="11111111-1111-1111-1111-111111111111",
        client_id="22222222-2222-2222-2222-222222222222",
        data_partition_id="",
        auth_method=AuthMethod.SERVICE_PRINCIPAL,
        client_secret="placeholder-secret",
    )
    page_module = _load_page(streamlit_recorder, monkeypatch)
    spy = _patch_services(page_module, monkeypatch)

    page_module.main()

    assert streamlit_recorder.calls_named("page_link")
    assert spy.list_calls == []


# ===========================================================================
# Autorun-once + Refresh
# ===========================================================================


def test_autorun_calls_list_and_properties_on_first_render(
    streamlit_recorder: StreamlitRecorder,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    streamlit_recorder.session_state[CONNECTION_KEY] = (
        _service_principal_connection()
    )
    page_module = _load_page(streamlit_recorder, monkeypatch)
    spy = _patch_services(page_module, monkeypatch)

    page_module.main()

    assert len(spy.list_calls) == 1
    assert spy.list_calls[0][2] is None  # valid filter off
    assert len(spy.properties_calls) == 1
    assert streamlit_recorder.session_state[AUTORUN_KEY] is True


def test_autorun_does_not_refire_on_second_render(
    streamlit_recorder: StreamlitRecorder,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    streamlit_recorder.session_state[CONNECTION_KEY] = (
        _service_principal_connection()
    )
    streamlit_recorder.session_state[AUTORUN_KEY] = True
    streamlit_recorder.session_state[LIST_KEY] = [_sample_tag()]
    streamlit_recorder.session_state[PROPERTIES_SPEC_KEY] = (
        _ok_properties_result().spec
    )
    page_module = _load_page(streamlit_recorder, monkeypatch)
    spy = _patch_services(page_module, monkeypatch)

    page_module.main()

    assert spy.list_calls == []
    assert spy.properties_calls == []


def test_refresh_button_bypasses_autorun_and_recalls_both(
    streamlit_recorder: StreamlitRecorder,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    streamlit_recorder.session_state[CONNECTION_KEY] = (
        _service_principal_connection()
    )
    streamlit_recorder.session_state[AUTORUN_KEY] = True
    streamlit_recorder.session_state[LIST_KEY] = [_sample_tag()]
    streamlit_recorder.button_responses[REFRESH_LABEL] = True
    page_module = _load_page(streamlit_recorder, monkeypatch)
    spy = _patch_services(page_module, monkeypatch)

    page_module.main()

    assert len(spy.list_calls) == 1
    assert len(spy.properties_calls) == 1


def test_show_valid_only_toggle_calls_list_with_valid_true(
    streamlit_recorder: StreamlitRecorder,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    streamlit_recorder.session_state[CONNECTION_KEY] = (
        _service_principal_connection()
    )
    streamlit_recorder.session_state[AUTORUN_KEY] = True
    # Operator already toggled the filter on; Refresh forwards the flag.
    streamlit_recorder.session_state[SHOW_VALID_ONLY_KEY] = True
    streamlit_recorder.widget_values[TOGGLE_LABEL] = True
    streamlit_recorder.button_responses[REFRESH_LABEL] = True
    page_module = _load_page(streamlit_recorder, monkeypatch)
    spy = _patch_services(page_module, monkeypatch)

    page_module.main()

    assert len(spy.list_calls) == 1
    assert spy.list_calls[0][2] is True


# ===========================================================================
# Selection: get_legal_tag fires lazily; cached on second select
# ===========================================================================


def test_selecting_tag_triggers_lazy_get_legal_tag(
    streamlit_recorder: StreamlitRecorder,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    streamlit_recorder.session_state[CONNECTION_KEY] = (
        _service_principal_connection()
    )
    streamlit_recorder.session_state[AUTORUN_KEY] = True
    streamlit_recorder.session_state[LIST_KEY] = [
        _sample_tag("opendes-tag-a"),
        _sample_tag("opendes-tag-b"),
    ]
    streamlit_recorder.session_state[PROPERTIES_SPEC_KEY] = (
        _ok_properties_result().spec
    )
    streamlit_recorder.widget_values["Select a tag to view details"] = (
        "opendes-tag-a"
    )
    page_module = _load_page(streamlit_recorder, monkeypatch)
    spy = _patch_services(page_module, monkeypatch)

    page_module.main()

    assert len(spy.get_calls) == 1
    assert spy.get_calls[0][2] == "opendes-tag-a"
    assert (
        streamlit_recorder.session_state[SELECTED_NAME_KEY]
        == "opendes-tag-a"
    )
    assert (
        streamlit_recorder.session_state[SELECTED_DETAIL_KEY] is not None
    )


def test_re_selecting_same_tag_does_not_recall_get(
    streamlit_recorder: StreamlitRecorder,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    streamlit_recorder.session_state[CONNECTION_KEY] = (
        _service_principal_connection()
    )
    streamlit_recorder.session_state[AUTORUN_KEY] = True
    tag = _sample_tag("opendes-tag-a")
    streamlit_recorder.session_state[LIST_KEY] = [tag]
    streamlit_recorder.session_state[SELECTED_NAME_KEY] = "opendes-tag-a"
    streamlit_recorder.session_state[SELECTED_DETAIL_KEY] = (
        _ok_detail_result(tag)
    )
    streamlit_recorder.widget_values["Select a tag to view details"] = (
        "opendes-tag-a"
    )
    page_module = _load_page(streamlit_recorder, monkeypatch)
    spy = _patch_services(page_module, monkeypatch)

    page_module.main()

    assert spy.get_calls == []


# ===========================================================================
# Edit mode
# ===========================================================================


def test_clicking_edit_button_enters_edit_mode(
    streamlit_recorder: StreamlitRecorder,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    streamlit_recorder.session_state[CONNECTION_KEY] = (
        _service_principal_connection()
    )
    streamlit_recorder.session_state[AUTORUN_KEY] = True
    tag = _sample_tag("opendes-tag-a")
    streamlit_recorder.session_state[LIST_KEY] = [tag]
    streamlit_recorder.session_state[SELECTED_NAME_KEY] = "opendes-tag-a"
    streamlit_recorder.session_state[SELECTED_DETAIL_KEY] = (
        _ok_detail_result(tag)
    )
    streamlit_recorder.button_responses[EDIT_BUTTON_LABEL] = True
    page_module = _load_page(streamlit_recorder, monkeypatch)
    _patch_services(page_module, monkeypatch)

    page_module.main()

    assert streamlit_recorder.session_state[EDIT_MODE_KEY] is True
    # Edit form fields seeded from tag.
    assert (
        streamlit_recorder.session_state[EDIT_DESCRIPTION_KEY]
        == "Public test tag"
    )
    assert (
        streamlit_recorder.session_state[EDIT_CONTRACT_KEY]
        == "No Contract Related"
    )


def test_save_in_edit_mode_calls_update_and_exits_edit_mode(
    streamlit_recorder: StreamlitRecorder,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    streamlit_recorder.session_state[CONNECTION_KEY] = (
        _service_principal_connection()
    )
    streamlit_recorder.session_state[AUTORUN_KEY] = True
    tag = _sample_tag("opendes-tag-a")
    streamlit_recorder.session_state[LIST_KEY] = [tag]
    streamlit_recorder.session_state[SELECTED_NAME_KEY] = "opendes-tag-a"
    streamlit_recorder.session_state[SELECTED_DETAIL_KEY] = (
        _ok_detail_result(tag)
    )
    streamlit_recorder.session_state[EDIT_MODE_KEY] = True
    streamlit_recorder.session_state[EDIT_DESCRIPTION_KEY] = "updated desc"
    streamlit_recorder.session_state[EDIT_CONTRACT_KEY] = "Renewal-2027"
    streamlit_recorder.session_state[EDIT_EXPIRATION_KEY] = date(
        2030, 1, 1
    )
    streamlit_recorder.submit_responses[SAVE_BUTTON_LABEL] = True
    page_module = _load_page(streamlit_recorder, monkeypatch)
    spy = _patch_services(page_module, monkeypatch)

    page_module.main()

    assert len(spy.update_calls) == 1
    call = spy.update_calls[0]
    assert call["name"] == "opendes-tag-a"
    assert call["description"] == "updated desc"
    # Mutable fields override the merged props.
    assert call["properties"]["contractId"] == "Renewal-2027"
    assert call["properties"]["expirationDate"] == "2030-01-01"
    assert streamlit_recorder.session_state[EDIT_MODE_KEY] is False


def test_save_failure_keeps_edit_mode_and_pins_sticky_error(
    streamlit_recorder: StreamlitRecorder,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    streamlit_recorder.session_state[CONNECTION_KEY] = (
        _service_principal_connection()
    )
    streamlit_recorder.session_state[AUTORUN_KEY] = True
    tag = _sample_tag("opendes-tag-a")
    streamlit_recorder.session_state[LIST_KEY] = [tag]
    streamlit_recorder.session_state[SELECTED_NAME_KEY] = "opendes-tag-a"
    streamlit_recorder.session_state[SELECTED_DETAIL_KEY] = (
        _ok_detail_result(tag)
    )
    streamlit_recorder.session_state[EDIT_MODE_KEY] = True
    streamlit_recorder.session_state[EDIT_DESCRIPTION_KEY] = "updated"
    streamlit_recorder.session_state[EDIT_CONTRACT_KEY] = "x"
    streamlit_recorder.session_state[EDIT_EXPIRATION_KEY] = date(
        2030, 1, 1
    )
    streamlit_recorder.submit_responses[SAVE_BUTTON_LABEL] = True
    fail = LegalTagDetailResult(
        tag=None,
        ok=False,
        http_status=400,
        error_message="bad request",
        correlation_id="corr-bad",
    )
    page_module = _load_page(streamlit_recorder, monkeypatch)
    _patch_services(page_module, monkeypatch, update_result=fail)

    page_module.main()

    assert streamlit_recorder.session_state[EDIT_MODE_KEY] is True
    err = streamlit_recorder.session_state[LAST_ERROR_KEY]
    assert isinstance(err, str)
    assert "Update" in err and "bad request" in err


# ===========================================================================
# Delete confirmation
# ===========================================================================


def test_delete_button_opens_confirmation_block(
    streamlit_recorder: StreamlitRecorder,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    streamlit_recorder.session_state[CONNECTION_KEY] = (
        _service_principal_connection()
    )
    streamlit_recorder.session_state[AUTORUN_KEY] = True
    tag = _sample_tag("opendes-tag-a")
    streamlit_recorder.session_state[LIST_KEY] = [tag]
    streamlit_recorder.session_state[SELECTED_NAME_KEY] = "opendes-tag-a"
    streamlit_recorder.session_state[SELECTED_DETAIL_KEY] = (
        _ok_detail_result(tag)
    )
    streamlit_recorder.button_responses[DELETE_BUTTON_LABEL] = True
    page_module = _load_page(streamlit_recorder, monkeypatch)
    spy = _patch_services(page_module, monkeypatch)

    page_module.main()

    assert (
        streamlit_recorder.session_state.get("_legal_tags_delete_open")
        is True
    )
    # Delete must NOT fire — only the confirm button does that.
    assert spy.delete_calls == []


def test_confirm_delete_disabled_until_typed_name_matches(
    streamlit_recorder: StreamlitRecorder,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    streamlit_recorder.session_state[CONNECTION_KEY] = (
        _service_principal_connection()
    )
    streamlit_recorder.session_state[AUTORUN_KEY] = True
    tag = _sample_tag("opendes-tag-a")
    streamlit_recorder.session_state[LIST_KEY] = [tag]
    streamlit_recorder.session_state[SELECTED_NAME_KEY] = "opendes-tag-a"
    streamlit_recorder.session_state[SELECTED_DETAIL_KEY] = (
        _ok_detail_result(tag)
    )
    streamlit_recorder.session_state["_legal_tags_delete_open"] = True
    # Typed text doesn't match the name.
    streamlit_recorder.widget_values["Type `opendes-tag-a` to confirm"] = (
        "wrong"
    )
    streamlit_recorder.button_responses[DELETE_CONFIRM_LABEL] = True
    page_module = _load_page(streamlit_recorder, monkeypatch)
    spy = _patch_services(page_module, monkeypatch)

    page_module.main()

    # disabled=True so button_responses path returns False → no delete call.
    assert spy.delete_calls == []
    confirm_calls = [
        call
        for call in streamlit_recorder.calls_named("button")
        if call.args and call.args[0] == DELETE_CONFIRM_LABEL
    ]
    assert confirm_calls
    assert confirm_calls[0].kwargs.get("disabled") is True


def test_confirm_delete_with_matching_name_calls_delete_and_refreshes(
    streamlit_recorder: StreamlitRecorder,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    streamlit_recorder.session_state[CONNECTION_KEY] = (
        _service_principal_connection()
    )
    streamlit_recorder.session_state[AUTORUN_KEY] = True
    tag = _sample_tag("opendes-tag-a")
    streamlit_recorder.session_state[LIST_KEY] = [tag]
    streamlit_recorder.session_state[SELECTED_NAME_KEY] = "opendes-tag-a"
    streamlit_recorder.session_state[SELECTED_DETAIL_KEY] = (
        _ok_detail_result(tag)
    )
    streamlit_recorder.session_state["_legal_tags_delete_open"] = True
    streamlit_recorder.widget_values["Type `opendes-tag-a` to confirm"] = (
        "opendes-tag-a"
    )
    streamlit_recorder.button_responses[DELETE_CONFIRM_LABEL] = True
    page_module = _load_page(streamlit_recorder, monkeypatch)
    spy = _patch_services(page_module, monkeypatch)

    page_module.main()

    assert len(spy.delete_calls) == 1
    assert spy.delete_calls[0][2] == "opendes-tag-a"
    # List must be refreshed after a successful delete.
    assert len(spy.list_calls) >= 1
    assert (
        streamlit_recorder.session_state[SELECTED_NAME_KEY] is None
    )


# ===========================================================================
# Create form: pre-validation gate + happy path + Suggest defaults
# ===========================================================================


def _populate_create_form(
    streamlit_recorder: StreamlitRecorder, *, name: str = "opendes-new"
) -> None:
    streamlit_recorder.session_state[FORM_NAME_KEY] = name
    streamlit_recorder.session_state[FORM_DESCRIPTION_KEY] = "desc"
    streamlit_recorder.session_state[FORM_COUNTRY_KEY] = ["US"]
    streamlit_recorder.session_state[FORM_CONTRACT_KEY] = (
        "No Contract Related"
    )
    streamlit_recorder.session_state[FORM_EXPIRATION_KEY] = date(2099, 12, 31)
    streamlit_recorder.session_state[FORM_ORIGINATOR_KEY] = "ADME Operator"
    streamlit_recorder.session_state[FORM_DATA_TYPE_KEY] = (
        "Public Domain Data"
    )
    streamlit_recorder.session_state[FORM_SECURITY_KEY] = "Public"
    streamlit_recorder.session_state[FORM_PERSONAL_DATA_KEY] = (
        "No Personal Data"
    )
    streamlit_recorder.session_state[FORM_EXPORT_KEY] = "EAR99"


def test_create_form_pre_validation_lists_each_missing_field(
    streamlit_recorder: StreamlitRecorder,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    streamlit_recorder.session_state[CONNECTION_KEY] = (
        _service_principal_connection()
    )
    streamlit_recorder.session_state[AUTORUN_KEY] = True
    # All fields blank → every required field flagged + no create call.
    streamlit_recorder.button_responses[CREATE_BUTTON_LABEL] = True
    page_module = _load_page(streamlit_recorder, monkeypatch)
    spy = _patch_services(page_module, monkeypatch)

    page_module.main()

    warning_messages = [
        call.args[0] for call in streamlit_recorder.calls_named("warning")
    ]
    assert warning_messages, "missing-field gate should warn"
    combined = "\n".join(warning_messages)
    for field_name in (
        "Name",
        "Description",
        "Country of origin",
        "Contract ID",
        "Originator",
        "Data type",
        "Security classification",
        "Personal data",
        "Export classification",
    ):
        assert field_name in combined, f"missing field {field_name!r} not surfaced"
    # Pre-form gate disables the Create button → no create call fired.
    assert spy.create_calls == []


def test_create_happy_path_calls_create_then_refreshes_list(
    streamlit_recorder: StreamlitRecorder,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    streamlit_recorder.session_state[CONNECTION_KEY] = (
        _service_principal_connection()
    )
    streamlit_recorder.session_state[AUTORUN_KEY] = True
    streamlit_recorder.session_state[PROPERTIES_SPEC_KEY] = (
        _ok_properties_result().spec
    )
    # Use partition-prefixed name so auto-prefix does not re-prepend.
    _populate_create_form(streamlit_recorder, name="example-opendes-new")
    streamlit_recorder.button_responses[CREATE_BUTTON_LABEL] = True
    page_module = _load_page(streamlit_recorder, monkeypatch)
    spy = _patch_services(page_module, monkeypatch)

    page_module.main()

    assert len(spy.create_calls) == 1
    call = spy.create_calls[0]
    assert call["name"] == "example-opendes-new"
    assert call["description"] == "desc"
    props = call["properties"]
    # Outbound payload uses server-shaped keys per Satya section 2.
    assert props["countryOfOrigin"] == ["US"]
    assert props["contractId"] == "No Contract Related"
    assert props["expirationDate"] == "2099-12-31"
    assert props["originator"] == "ADME Operator"
    assert props["dataType"] == "Public Domain Data"
    assert props["securityClassification"] == "Public"
    assert props["personalData"] == "No Personal Data"
    assert props["exportClassification"] == "EAR99"
    # List refresh ran after the successful create.
    assert len(spy.list_calls) >= 1
    # New tag is selected in the detail panel.
    assert (
        streamlit_recorder.session_state[SELECTED_NAME_KEY]
        == "example-opendes-new"
    )


def test_suggest_defaults_button_populates_form_keys(
    streamlit_recorder: StreamlitRecorder,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    streamlit_recorder.session_state[CONNECTION_KEY] = (
        _service_principal_connection()
    )
    streamlit_recorder.session_state[AUTORUN_KEY] = True
    streamlit_recorder.session_state[PROPERTIES_SPEC_KEY] = (
        _ok_properties_result().spec
    )
    streamlit_recorder.button_responses[SUGGEST_DEFAULTS_LABEL] = True
    page_module = _load_page(streamlit_recorder, monkeypatch)
    spy = _patch_services(page_module, monkeypatch)

    page_module.main()

    assert (
        streamlit_recorder.session_state[FORM_NAME_KEY]
        == "example-opendes-default-legal-tag"
    )
    assert streamlit_recorder.session_state[FORM_COUNTRY_KEY] == ["US"]
    assert (
        streamlit_recorder.session_state[FORM_CONTRACT_KEY]
        == "No Contract Related"
    )
    assert (
        streamlit_recorder.session_state[FORM_DATA_TYPE_KEY]
        == "Public Domain Data"
    )
    assert streamlit_recorder.session_state[FORM_SECURITY_KEY] == "Public"
    assert (
        streamlit_recorder.session_state[FORM_PERSONAL_DATA_KEY]
        == "No Personal Data"
    )
    assert streamlit_recorder.session_state[FORM_EXPORT_KEY] == "EAR99"
    # Suggest does NOT submit the form.
    assert spy.create_calls == []


# ===========================================================================
# Properties endpoint 404 → fallback flag + banner
# ===========================================================================


def test_properties_404_sets_fallback_flag_and_renders_banner(
    streamlit_recorder: StreamlitRecorder,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    streamlit_recorder.session_state[CONNECTION_KEY] = (
        _service_principal_connection()
    )
    page_module = _load_page(streamlit_recorder, monkeypatch)
    _patch_services(
        page_module,
        monkeypatch,
        properties_result=_failed_properties_404(),
    )

    page_module.main()

    assert (
        streamlit_recorder.session_state[PROPERTIES_FALLBACK_KEY] is True
    )
    assert streamlit_recorder.session_state[PROPERTIES_SPEC_KEY] is None
    # Some banner is rendered to flag the fallback (info or warning).
    info_msgs = [
        str(call.args[0]) for call in streamlit_recorder.calls_named("info")
    ]
    warn_msgs = [
        str(call.args[0])
        for call in streamlit_recorder.calls_named("warning")
    ]
    assert info_msgs or warn_msgs


# ===========================================================================
# Sticky error
# ===========================================================================


def test_list_failure_pins_sticky_error_at_top_of_page(
    streamlit_recorder: StreamlitRecorder,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    streamlit_recorder.session_state[CONNECTION_KEY] = (
        _service_principal_connection()
    )
    fail = LegalTagListResult(
        ok=False,
        http_status=500,
        error_message="boom",
        correlation_id="corr-x",
    )
    page_module = _load_page(streamlit_recorder, monkeypatch)
    _patch_services(page_module, monkeypatch, list_result=fail)

    page_module.main()

    err = streamlit_recorder.session_state[LAST_ERROR_KEY]
    assert isinstance(err, str)
    assert "List failed" in err and "boom" in err


def test_dismiss_error_button_clears_sticky_error(
    streamlit_recorder: StreamlitRecorder,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    streamlit_recorder.session_state[CONNECTION_KEY] = (
        _service_principal_connection()
    )
    streamlit_recorder.session_state[AUTORUN_KEY] = True
    streamlit_recorder.session_state[LAST_ERROR_KEY] = "stale error"
    streamlit_recorder.button_responses[DISMISS_ERROR_LABEL] = True
    page_module = _load_page(streamlit_recorder, monkeypatch)
    _patch_services(page_module, monkeypatch)

    page_module.main()

    assert streamlit_recorder.session_state[LAST_ERROR_KEY] is None


# ===========================================================================
# History panel
# ===========================================================================


def test_history_appends_one_row_per_api_call_with_correct_label(
    streamlit_recorder: StreamlitRecorder,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    streamlit_recorder.session_state[CONNECTION_KEY] = (
        _service_principal_connection()
    )
    page_module = _load_page(streamlit_recorder, monkeypatch)
    _patch_services(page_module, monkeypatch)

    page_module.main()

    history = streamlit_recorder.session_state[HISTORY_KEY]
    assert isinstance(history, list)
    labels = [entry["endpoint"] for entry in history]
    assert "legaltags.list" in labels
    assert "legaltags.properties" in labels


def test_clear_history_button_empties_history(
    streamlit_recorder: StreamlitRecorder,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    streamlit_recorder.session_state[CONNECTION_KEY] = (
        _service_principal_connection()
    )
    streamlit_recorder.session_state[AUTORUN_KEY] = True
    streamlit_recorder.session_state[HISTORY_KEY] = [
        {
            "timestamp": "2026-05-07T10:00:00Z",
            "endpoint": "legaltags.list",
            "latency_ms": 10.0,
            "http_status": 200,
            "ok": True,
        }
    ]
    streamlit_recorder.button_responses[CLEAR_HISTORY_LABEL] = True
    page_module = _load_page(streamlit_recorder, monkeypatch)
    _patch_services(page_module, monkeypatch)

    page_module.main()

    assert streamlit_recorder.session_state[HISTORY_KEY] == []
