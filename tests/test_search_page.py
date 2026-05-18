"""Tests for the ADME Search page (`app/pages/7_🔍_Search.py`)."""

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
from app.models.connection import ADMEConnection, AuthMethod
from app.models.osdu import (
    KindAggregationResult,
    RecordDetailResult,
    RecordSummary,
    SearchPageResult,
)
from tests.support.streamlit_recorder import StreamlitRecorder

SEARCH_PAGE_PATH = (
    Path(__file__).resolve().parents[1]
    / "app"
    / "pages"
    / "7_🔍_Search.py"
)

# Locked session-state keys mirror those in the page.
QUERY_TEXT_KEY = "search_query_text"
KIND_FILTER_KEY = "search_kind_filter"
KIND_OPTIONS_KEY = "search_kind_options"
RESULTS_KEY = "search_results"
TOTAL_COUNT_KEY = "search_total_count"
PAGE_OFFSET_KEY = "search_page_offset"
HISTORY_KEY = "search_history"
LAST_ERROR_KEY = "search_last_error"
SELECTED_RECORD_ID_KEY = "search_selected_record_id"
FULL_RECORD_CACHE_KEY = "search_full_record_cache"
AUTORUN_DONE_KEY = "search_autorun_done"
RESOLVED_QUERY_KEY = "search_resolved_query"

WILDCARD_KIND = "*:*:*:*"

# Button / widget labels (verbatim — page contract).
REFRESH_LABEL = "🔄 Refresh"
SEARCH_LABEL = "🔍 Search"
PREV_LABEL = "« Prev"
NEXT_LABEL = "Next »"
DISMISS_LABEL = "Dismiss error"
CLEAR_HISTORY_LABEL = "Clear history"
FETCH_FULL_LABEL = "📥 Fetch full record"
REFRESH_FULL_LABEL = "🔄 Refresh full record"
KIND_SELECT_LABEL = "Kind"
QUERY_INPUT_LABEL = "Free-text query (Lucene syntax)"
RECORD_SELECTOR_LABEL = "Select a record to inspect"


# ---------------------------------------------------------------------------
# Module loader
# ---------------------------------------------------------------------------


def _load_page(
    streamlit_recorder: StreamlitRecorder,
    monkeypatch: pytest.MonkeyPatch,
) -> ModuleType:
    monkeypatch.setitem(sys.modules, "streamlit", streamlit_recorder)
    module_name = "tests.generated_search_page"
    sys.modules.pop(module_name, None)
    spec = importlib.util.spec_from_file_location(
        module_name, SEARCH_PAGE_PATH
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


def _summary(record_id: str = "opendes:doc:1") -> RecordSummary:
    return RecordSummary(
        id=record_id,
        kind="osdu:wks:reference-data:1.0.0",
        create_time="2024-01-01T00:00:00Z",
        version=1,
        source={"data": {"foo": "bar"}},
    )


def _ok_kinds() -> KindAggregationResult:
    return KindAggregationResult(
        kinds=["osdu:wks:reference-data:1.0.0", "osdu:wks:dataset:1.0.0"],
        from_aggregation=True,
        ok=True,
        http_status=200,
        latency_ms=12.0,
        correlation_id="corr-kinds",
    )


def _ok_search(
    *,
    records: list[RecordSummary] | None = None,
    offset: int = 0,
    total: int | None = 100,
) -> SearchPageResult:
    recs = records if records is not None else [_summary()]
    return SearchPageResult(
        kind="osdu:wks:reference-data:1.0.0",
        offset=offset,
        limit=100,
        records=recs,
        total_count=total,
        has_more=total is not None and offset + len(recs) < total,
        ok=True,
        http_status=200,
        latency_ms=22.0,
        correlation_id="corr-search",
    )


def _failed_search_400() -> SearchPageResult:
    return SearchPageResult(
        kind="*:*:*:*",
        offset=0,
        limit=100,
        ok=False,
        http_status=400,
        latency_ms=8.0,
        correlation_id="corr-400",
        error_message="invalid lucene syntax",
    )


def _ok_get_record() -> RecordDetailResult:
    return RecordDetailResult(
        record_id="opendes:doc:1",
        record={"id": "opendes:doc:1", "data": {"foo": "bar"}},
        ok=True,
        http_status=200,
        latency_ms=15.0,
        correlation_id="corr-rec",
    )


def _missing_get_record() -> RecordDetailResult:
    return RecordDetailResult(
        record_id="opendes:doc:1",
        record=None,
        ok=False,
        http_status=404,
        latency_ms=5.0,
        correlation_id="corr-404",
        error_message="Record 'opendes:doc:1' not found or not visible.",
    )


# ---------------------------------------------------------------------------
# Service spy
# ---------------------------------------------------------------------------


class _Spy:
    def __init__(self) -> None:
        self.list_kinds_calls: list[Any] = []
        self.search_calls: list[dict[str, Any]] = []
        self.get_record_calls: list[tuple[Any, str, str]] = []
        self.token_calls: list[Any] = []


def _patch_services(
    page_module: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    *,
    kinds_result: KindAggregationResult | None = None,
    search_result: SearchPageResult | None = None,
    record_result: RecordDetailResult | None = None,
    token: str | None = "test-token",
) -> _Spy:
    spy = _Spy()

    def fake_get_token(connection: ADMEConnection, **_: Any) -> str:
        spy.token_calls.append(connection)
        if token is None:
            from app.services.auth import AuthenticationError

            raise AuthenticationError("no token")
        return token

    def fake_list_kinds(
        connection: ADMEConnection, supplied_token: str
    ) -> KindAggregationResult:
        spy.list_kinds_calls.append((connection, supplied_token))
        return kinds_result if kinds_result is not None else _ok_kinds()

    def fake_search(
        connection: ADMEConnection,
        supplied_token: str,
        *,
        kind: str,
        query: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> SearchPageResult:
        spy.search_calls.append(
            {
                "connection": connection,
                "token": supplied_token,
                "kind": kind,
                "query": query,
                "limit": limit,
                "offset": offset,
            }
        )
        return search_result if search_result is not None else _ok_search()

    def fake_get_record(
        connection: ADMEConnection,
        supplied_token: str,
        record_id: str,
    ) -> RecordDetailResult:
        spy.get_record_calls.append((connection, supplied_token, record_id))
        return record_result if record_result is not None else _ok_get_record()

    monkeypatch.setattr(page_module, "get_token", fake_get_token)
    monkeypatch.setattr(page_module, "list_kinds", fake_list_kinds)
    monkeypatch.setattr(page_module, "search_records", fake_search)
    monkeypatch.setattr(page_module, "get_record", fake_get_record)
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
    assert spy.list_kinds_calls == []
    assert spy.search_calls == []
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

    page_link_calls = streamlit_recorder.calls_named("page_link")
    assert page_link_calls
    info_messages = [
        call.args[0] for call in streamlit_recorder.calls_named("info")
    ]
    assert any("Instance Configuration" in m for m in info_messages)
    assert spy.list_kinds_calls == []
    assert spy.search_calls == []


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
    info_messages = [
        call.args[0] for call in streamlit_recorder.calls_named("info")
    ]
    assert any("Instance Configuration" in m for m in info_messages)
    assert spy.list_kinds_calls == []
    assert spy.search_calls == []


# ===========================================================================
# Autorun-once
# ===========================================================================


def test_autorun_fires_list_kinds_and_search_on_first_render(
    streamlit_recorder: StreamlitRecorder,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    streamlit_recorder.session_state[CONNECTION_KEY] = (
        _service_principal_connection()
    )
    page_module = _load_page(streamlit_recorder, monkeypatch)
    spy = _patch_services(page_module, monkeypatch)

    page_module.main()

    assert len(spy.list_kinds_calls) == 1
    assert len(spy.search_calls) == 1
    assert streamlit_recorder.session_state[AUTORUN_DONE_KEY] is True
    # Kind options populated.
    options = streamlit_recorder.session_state[KIND_OPTIONS_KEY]
    assert isinstance(options, list)
    assert options[0] == WILDCARD_KIND
    assert "osdu:wks:reference-data:1.0.0" in options


def test_autorun_does_not_refire_on_second_render(
    streamlit_recorder: StreamlitRecorder,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    streamlit_recorder.session_state[CONNECTION_KEY] = (
        _service_principal_connection()
    )
    streamlit_recorder.session_state[AUTORUN_DONE_KEY] = True
    streamlit_recorder.session_state[KIND_OPTIONS_KEY] = [WILDCARD_KIND]
    streamlit_recorder.session_state[RESULTS_KEY] = [_summary()]
    page_module = _load_page(streamlit_recorder, monkeypatch)
    spy = _patch_services(page_module, monkeypatch)

    page_module.main()

    assert spy.list_kinds_calls == []
    assert spy.search_calls == []


def test_refresh_button_bypasses_autorun_guard(
    streamlit_recorder: StreamlitRecorder,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    streamlit_recorder.session_state[CONNECTION_KEY] = (
        _service_principal_connection()
    )
    streamlit_recorder.session_state[AUTORUN_DONE_KEY] = True
    streamlit_recorder.session_state[KIND_OPTIONS_KEY] = [WILDCARD_KIND]
    streamlit_recorder.session_state[RESULTS_KEY] = [_summary()]
    streamlit_recorder.button_responses[REFRESH_LABEL] = True
    page_module = _load_page(streamlit_recorder, monkeypatch)
    spy = _patch_services(page_module, monkeypatch)

    page_module.main()

    # Refresh forces a list_kinds + search even though autorun_done=True.
    assert len(spy.list_kinds_calls) == 1
    assert len(spy.search_calls) == 1
    # Pagination resets.
    assert streamlit_recorder.session_state[PAGE_OFFSET_KEY] == 0


# ===========================================================================
# Search execution
# ===========================================================================


def test_search_button_calls_search_with_selected_kind_and_query(
    streamlit_recorder: StreamlitRecorder,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    streamlit_recorder.session_state[CONNECTION_KEY] = (
        _service_principal_connection()
    )
    streamlit_recorder.session_state[AUTORUN_DONE_KEY] = True
    streamlit_recorder.session_state[KIND_OPTIONS_KEY] = [
        WILDCARD_KIND,
        "osdu:wks:reference-data:1.0.0",
    ]
    streamlit_recorder.session_state[KIND_FILTER_KEY] = (
        "osdu:wks:reference-data:1.0.0"
    )
    streamlit_recorder.widget_values[KIND_SELECT_LABEL] = (
        "osdu:wks:reference-data:1.0.0"
    )
    streamlit_recorder.widget_values[QUERY_INPUT_LABEL] = "data.foo:bar"
    # The text_input below the toolbar writes its value to session_state
    # via the bound key — the recorder doesn't auto-bind, so set it.
    streamlit_recorder.session_state[QUERY_TEXT_KEY] = "data.foo:bar"
    streamlit_recorder.button_responses[SEARCH_LABEL] = True
    page_module = _load_page(streamlit_recorder, monkeypatch)
    spy = _patch_services(page_module, monkeypatch)

    page_module.main()

    assert len(spy.search_calls) == 1
    call = spy.search_calls[0]
    assert call["kind"] == "osdu:wks:reference-data:1.0.0"
    assert call["query"] == "data.foo:bar"
    assert call["offset"] == 0
    assert streamlit_recorder.session_state[RESOLVED_QUERY_KEY] == (
        "data.foo:bar"
    )


def test_blank_query_passed_through_as_none(
    streamlit_recorder: StreamlitRecorder,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    streamlit_recorder.session_state[CONNECTION_KEY] = (
        _service_principal_connection()
    )
    page_module = _load_page(streamlit_recorder, monkeypatch)
    spy = _patch_services(page_module, monkeypatch)

    page_module.main()

    # Autorun search with empty resolved query.
    assert spy.search_calls
    assert spy.search_calls[0]["query"] in (None, "")


# ===========================================================================
# Empty results + missing kind list
# ===========================================================================


def test_empty_results_render_friendly_message(
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
        search_result=_ok_search(records=[], total=0),
    )

    page_module.main()

    info_messages = [
        call.args[0] for call in streamlit_recorder.calls_named("info")
    ]
    assert any("No records matched" in m for m in info_messages)


def test_kind_list_unavailable_shows_caption_and_wildcard_still_works(
    streamlit_recorder: StreamlitRecorder,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    streamlit_recorder.session_state[CONNECTION_KEY] = (
        _service_principal_connection()
    )
    empty_kinds = KindAggregationResult(
        kinds=[],
        from_aggregation=False,
        ok=True,
        http_status=200,
        latency_ms=5.0,
    )
    page_module = _load_page(streamlit_recorder, monkeypatch)
    spy = _patch_services(
        page_module, monkeypatch, kinds_result=empty_kinds
    )

    page_module.main()

    caption_texts = [
        call.args[0] for call in streamlit_recorder.calls_named("caption")
    ]
    assert any(
        "Kind list unavailable" in c for c in caption_texts
    ), f"Expected 'Kind list unavailable' caption; got {caption_texts!r}"

    # Wildcard option still in the options list.
    options = streamlit_recorder.session_state[KIND_OPTIONS_KEY]
    assert options == [WILDCARD_KIND]
    # Search still fired against wildcard.
    assert spy.search_calls
    assert spy.search_calls[0]["kind"] == WILDCARD_KIND


# ===========================================================================
# Pagination
# ===========================================================================


def test_pagination_prev_disabled_at_offset_zero(
    streamlit_recorder: StreamlitRecorder,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    streamlit_recorder.session_state[CONNECTION_KEY] = (
        _service_principal_connection()
    )
    streamlit_recorder.session_state[AUTORUN_DONE_KEY] = True
    streamlit_recorder.session_state[KIND_OPTIONS_KEY] = [WILDCARD_KIND]
    streamlit_recorder.session_state[RESULTS_KEY] = [_summary()]
    streamlit_recorder.session_state[TOTAL_COUNT_KEY] = 500
    streamlit_recorder.session_state[PAGE_OFFSET_KEY] = 0
    page_module = _load_page(streamlit_recorder, monkeypatch)
    _patch_services(page_module, monkeypatch)

    page_module.main()

    prev_buttons = [
        call
        for call in streamlit_recorder.calls_named("button")
        if call.args[0] == PREV_LABEL
    ]
    assert prev_buttons
    assert prev_buttons[0].kwargs.get("disabled") is True


def test_pagination_next_disabled_when_past_total(
    streamlit_recorder: StreamlitRecorder,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    streamlit_recorder.session_state[CONNECTION_KEY] = (
        _service_principal_connection()
    )
    streamlit_recorder.session_state[AUTORUN_DONE_KEY] = True
    streamlit_recorder.session_state[KIND_OPTIONS_KEY] = [WILDCARD_KIND]
    # Single page of results, total <= offset+len, so Next disabled.
    streamlit_recorder.session_state[RESULTS_KEY] = [_summary()]
    streamlit_recorder.session_state[TOTAL_COUNT_KEY] = 1
    streamlit_recorder.session_state[PAGE_OFFSET_KEY] = 0
    page_module = _load_page(streamlit_recorder, monkeypatch)
    _patch_services(page_module, monkeypatch)

    page_module.main()

    next_buttons = [
        call
        for call in streamlit_recorder.calls_named("button")
        if call.args[0] == NEXT_LABEL
    ]
    assert next_buttons
    assert next_buttons[0].kwargs.get("disabled") is True


def test_pagination_next_disabled_at_ceiling(
    streamlit_recorder: StreamlitRecorder,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    streamlit_recorder.session_state[CONNECTION_KEY] = (
        _service_principal_connection()
    )
    streamlit_recorder.session_state[AUTORUN_DONE_KEY] = True
    streamlit_recorder.session_state[KIND_OPTIONS_KEY] = [WILDCARD_KIND]
    # Full page at offset 9900: next would put offset+limit at 10100 > 10000.
    streamlit_recorder.session_state[RESULTS_KEY] = [
        _summary(f"id-{i}") for i in range(100)
    ]
    streamlit_recorder.session_state[TOTAL_COUNT_KEY] = 1_000_000
    streamlit_recorder.session_state[PAGE_OFFSET_KEY] = 9900
    page_module = _load_page(streamlit_recorder, monkeypatch)
    _patch_services(page_module, monkeypatch)

    page_module.main()

    next_buttons = [
        call
        for call in streamlit_recorder.calls_named("button")
        if call.args[0] == NEXT_LABEL
    ]
    assert next_buttons
    assert next_buttons[0].kwargs.get("disabled") is True


def test_pagination_next_button_advances_offset(
    streamlit_recorder: StreamlitRecorder,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    streamlit_recorder.session_state[CONNECTION_KEY] = (
        _service_principal_connection()
    )
    streamlit_recorder.session_state[AUTORUN_DONE_KEY] = True
    streamlit_recorder.session_state[KIND_OPTIONS_KEY] = [WILDCARD_KIND]
    streamlit_recorder.session_state[RESULTS_KEY] = [
        _summary(f"id-{i}") for i in range(100)
    ]
    streamlit_recorder.session_state[TOTAL_COUNT_KEY] = 500
    streamlit_recorder.session_state[PAGE_OFFSET_KEY] = 0
    streamlit_recorder.button_responses[NEXT_LABEL] = True
    page_module = _load_page(streamlit_recorder, monkeypatch)
    spy = _patch_services(
        page_module,
        monkeypatch,
        search_result=_ok_search(
            records=[_summary(f"id-{i}") for i in range(100)],
            offset=100,
            total=500,
        ),
    )

    page_module.main()

    assert spy.search_calls, "Next click should have triggered a search"
    assert spy.search_calls[-1]["offset"] == 100


def test_pagination_prev_button_decrements_offset(
    streamlit_recorder: StreamlitRecorder,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    streamlit_recorder.session_state[CONNECTION_KEY] = (
        _service_principal_connection()
    )
    streamlit_recorder.session_state[AUTORUN_DONE_KEY] = True
    streamlit_recorder.session_state[KIND_OPTIONS_KEY] = [WILDCARD_KIND]
    streamlit_recorder.session_state[RESULTS_KEY] = [_summary()]
    streamlit_recorder.session_state[TOTAL_COUNT_KEY] = 500
    streamlit_recorder.session_state[PAGE_OFFSET_KEY] = 200
    streamlit_recorder.button_responses[PREV_LABEL] = True
    page_module = _load_page(streamlit_recorder, monkeypatch)
    spy = _patch_services(
        page_module,
        monkeypatch,
        search_result=_ok_search(offset=100, total=500),
    )

    page_module.main()

    assert spy.search_calls
    assert spy.search_calls[-1]["offset"] == 100


# ===========================================================================
# Record selection + Fetch full record
# ===========================================================================


def test_selecting_record_persists_selection(
    streamlit_recorder: StreamlitRecorder,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    streamlit_recorder.session_state[CONNECTION_KEY] = (
        _service_principal_connection()
    )
    streamlit_recorder.session_state[AUTORUN_DONE_KEY] = True
    streamlit_recorder.session_state[KIND_OPTIONS_KEY] = [WILDCARD_KIND]
    streamlit_recorder.session_state[RESULTS_KEY] = [_summary("opendes:doc:1")]
    streamlit_recorder.session_state[PAGE_OFFSET_KEY] = 0
    streamlit_recorder.widget_values[RECORD_SELECTOR_LABEL] = "opendes:doc:1"
    page_module = _load_page(streamlit_recorder, monkeypatch)
    _patch_services(page_module, monkeypatch)

    page_module.main()

    assert (
        streamlit_recorder.session_state[SELECTED_RECORD_ID_KEY]
        == "opendes:doc:1"
    )
    subheaders = [
        call.args[0] for call in streamlit_recorder.calls_named("subheader")
    ]
    assert any("Selected record" in s for s in subheaders)


def test_fetch_full_record_button_calls_get_record_and_caches(
    streamlit_recorder: StreamlitRecorder,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    streamlit_recorder.session_state[CONNECTION_KEY] = (
        _service_principal_connection()
    )
    streamlit_recorder.session_state[AUTORUN_DONE_KEY] = True
    streamlit_recorder.session_state[KIND_OPTIONS_KEY] = [WILDCARD_KIND]
    streamlit_recorder.session_state[RESULTS_KEY] = [_summary("opendes:doc:1")]
    streamlit_recorder.session_state[SELECTED_RECORD_ID_KEY] = "opendes:doc:1"
    streamlit_recorder.widget_values[RECORD_SELECTOR_LABEL] = "opendes:doc:1"
    streamlit_recorder.button_responses[FETCH_FULL_LABEL] = True
    page_module = _load_page(streamlit_recorder, monkeypatch)
    spy = _patch_services(page_module, monkeypatch)

    page_module.main()

    assert len(spy.get_record_calls) == 1
    assert spy.get_record_calls[0][2] == "opendes:doc:1"
    cache = streamlit_recorder.session_state[FULL_RECORD_CACHE_KEY]
    assert isinstance(cache, dict)
    assert "opendes:doc:1" in cache
    cached_record = cache["opendes:doc:1"]
    assert isinstance(cached_record, dict)
    assert cached_record["id"] == "opendes:doc:1"


def test_fetch_full_record_404_sets_sticky_error(
    streamlit_recorder: StreamlitRecorder,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    streamlit_recorder.session_state[CONNECTION_KEY] = (
        _service_principal_connection()
    )
    streamlit_recorder.session_state[AUTORUN_DONE_KEY] = True
    streamlit_recorder.session_state[KIND_OPTIONS_KEY] = [WILDCARD_KIND]
    streamlit_recorder.session_state[RESULTS_KEY] = [_summary("opendes:doc:1")]
    streamlit_recorder.session_state[SELECTED_RECORD_ID_KEY] = "opendes:doc:1"
    streamlit_recorder.widget_values[RECORD_SELECTOR_LABEL] = "opendes:doc:1"
    streamlit_recorder.button_responses[FETCH_FULL_LABEL] = True
    page_module = _load_page(streamlit_recorder, monkeypatch)
    _patch_services(
        page_module, monkeypatch, record_result=_missing_get_record()
    )

    page_module.main()

    err = streamlit_recorder.session_state[LAST_ERROR_KEY]
    assert isinstance(err, str)
    assert "opendes:doc:1" in err
    assert "not found" in err.lower() or "not visible" in err.lower()


# ===========================================================================
# Sticky error / Dismiss / 400 bad Lucene
# ===========================================================================


def test_search_400_bad_lucene_sets_sticky_error_and_does_not_crash(
    streamlit_recorder: StreamlitRecorder,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    streamlit_recorder.session_state[CONNECTION_KEY] = (
        _service_principal_connection()
    )
    page_module = _load_page(streamlit_recorder, monkeypatch)
    _patch_services(
        page_module, monkeypatch, search_result=_failed_search_400()
    )

    page_module.main()

    err = streamlit_recorder.session_state[LAST_ERROR_KEY]
    assert isinstance(err, str)
    assert "invalid lucene syntax" in err
    # Sticky error key set for the *next* render (the page renders the
    # sticky banner above the toolbar, so it appears on the rerun
    # triggered by the failing call). The page must not crash.
    assert streamlit_recorder.session_state[AUTORUN_DONE_KEY] is True


def test_dismiss_error_clears_sticky_key(
    streamlit_recorder: StreamlitRecorder,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    streamlit_recorder.session_state[CONNECTION_KEY] = (
        _service_principal_connection()
    )
    streamlit_recorder.session_state[AUTORUN_DONE_KEY] = True
    streamlit_recorder.session_state[KIND_OPTIONS_KEY] = [WILDCARD_KIND]
    streamlit_recorder.session_state[LAST_ERROR_KEY] = "❌ Existing error"
    streamlit_recorder.button_responses[DISMISS_LABEL] = True
    page_module = _load_page(streamlit_recorder, monkeypatch)
    _patch_services(page_module, monkeypatch)

    page_module.main()

    assert streamlit_recorder.session_state[LAST_ERROR_KEY] is None


# ===========================================================================
# History dataframe + clear
# ===========================================================================


def test_history_dataframe_renders_when_history_present(
    streamlit_recorder: StreamlitRecorder,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    streamlit_recorder.session_state[CONNECTION_KEY] = (
        _service_principal_connection()
    )
    page_module = _load_page(streamlit_recorder, monkeypatch)
    _patch_services(page_module, monkeypatch)

    page_module.main()

    # Autorun pushed two history entries (list-kinds + search).
    history = streamlit_recorder.session_state[HISTORY_KEY]
    assert isinstance(history, list)
    assert len(history) >= 2
    # Subheader rendered.
    subheaders = [
        call.args[0] for call in streamlit_recorder.calls_named("subheader")
    ]
    assert any("Session history" in s for s in subheaders)


def test_clear_history_button_resets_history(
    streamlit_recorder: StreamlitRecorder,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    streamlit_recorder.session_state[CONNECTION_KEY] = (
        _service_principal_connection()
    )
    streamlit_recorder.session_state[AUTORUN_DONE_KEY] = True
    streamlit_recorder.session_state[KIND_OPTIONS_KEY] = [WILDCARD_KIND]
    streamlit_recorder.session_state[HISTORY_KEY] = [
        {
            "timestamp": "2026-05-11T00:00:00Z",
            "endpoint": "search.k",
            "ok": True,
            "http_status": 200,
            "latency_ms": 12.0,
            "correlation_id": "corr-1",
            "error_message": None,
        }
    ]
    streamlit_recorder.button_responses[CLEAR_HISTORY_LABEL] = True
    page_module = _load_page(streamlit_recorder, monkeypatch)
    _patch_services(page_module, monkeypatch)

    page_module.main()

    assert streamlit_recorder.session_state[HISTORY_KEY] == []


# ===========================================================================
# Session-key contract — Satya's lock
# ===========================================================================


def test_all_locked_session_keys_initialized(
    streamlit_recorder: StreamlitRecorder,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    streamlit_recorder.session_state[CONNECTION_KEY] = (
        _service_principal_connection()
    )
    page_module = _load_page(streamlit_recorder, monkeypatch)
    _patch_services(page_module, monkeypatch)

    page_module.main()

    locked_keys = [
        QUERY_TEXT_KEY,
        KIND_FILTER_KEY,
        KIND_OPTIONS_KEY,
        RESULTS_KEY,
        TOTAL_COUNT_KEY,
        PAGE_OFFSET_KEY,
        HISTORY_KEY,
        LAST_ERROR_KEY,
        SELECTED_RECORD_ID_KEY,
        FULL_RECORD_CACHE_KEY,
        AUTORUN_DONE_KEY,
    ]
    for key in locked_keys:
        assert key in streamlit_recorder.session_state, (
            f"Locked session key missing: {key}"
        )
