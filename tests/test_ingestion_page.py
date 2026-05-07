"""Tests for the ADME manifest-ingestion page (`app/pages/4_📥_Ingestion.py`)."""

from __future__ import annotations

import importlib.util
import json
import sys
from datetime import UTC, datetime, timedelta
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
    LegalTagCheckResult,
    SearchResult,
    WorkflowRunResult,
    WorkflowStatus,
)
from tests.support.streamlit_recorder import StreamlitRecorder

INGESTION_PAGE_PATH = (
    Path(__file__).resolve().parents[1]
    / "app"
    / "pages"
    / "4_📥_Ingestion.py"
)

# Locked session keys (per Judson's contract — Charlie tests these names).
MANIFEST_TEXT_KEY = "ingestion_manifest_text"
LEGAL_TAG_KEY = "ingestion_legal_tag"
ACL_OWNERS_KEY = "ingestion_acl_owners"
ACL_VIEWERS_KEY = "ingestion_acl_viewers"
RUN_ID_KEY = "ingestion_run_id"
SUBMIT_STARTED_AT_KEY = "ingestion_submit_started_at"
KINDS_KEY = "ingestion_kinds"
WORKFLOW_STATUS_KEY = "ingestion_workflow_status"
LAST_POLL_AT_KEY = "ingestion_last_poll_at"
POLLING_ACTIVE_KEY = "ingestion_polling_active"
HISTORY_KEY = "ingestion_history"
VERIFICATION_DONE_KEY = "ingestion_verification_done"

VALIDATE_LABEL = "Validate & Ingest"
INSERT_SAMPLE_LABEL = "Insert TNO sample into editor"
REFRESH_LABEL = "🔄 Refresh status now"
CLEAR_HISTORY_TOP_LABEL = "Clear history"
CLEAR_HISTORY_BOTTOM_LABEL = "🧹 Clear history"

KIND_A = "osdu:wks:reference-data--AliasNameType:1.0.0"
KIND_B = "osdu:wks:master-data--Wellbore:1.0.0"

VALID_MANIFEST_TEXT = json.dumps(
    {
        "executionContext": {
            "manifest": {"ReferenceData": [{"kind": KIND_A}]}
        }
    }
)

VALID_MANIFEST_TWO_SECTIONS_TEXT = json.dumps(
    {
        "executionContext": {
            "manifest": {
                "ReferenceData": [{"kind": KIND_A}],
                "MasterData": [{"kind": KIND_B}],
            }
        }
    }
)


# ---------------------------------------------------------------------------
# Module loader (mirror of the entitlements page test pattern)
# ---------------------------------------------------------------------------


def _load_ingestion_module(
    streamlit_recorder: StreamlitRecorder,
    monkeypatch: pytest.MonkeyPatch,
) -> ModuleType:
    monkeypatch.setitem(sys.modules, "streamlit", streamlit_recorder)
    module_name = "tests.generated_ingestion_page"
    sys.modules.pop(module_name, None)
    spec = importlib.util.spec_from_file_location(
        module_name, INGESTION_PAGE_PATH
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


def _ok_legal_result() -> LegalTagCheckResult:
    return LegalTagCheckResult(
        name="opendes-open-test",
        ok=True,
        http_status=200,
        latency_ms=10.0,
        correlation_id="corr-legal",
    )


def _failed_legal_result() -> LegalTagCheckResult:
    return LegalTagCheckResult(
        name="opendes-open-test",
        ok=False,
        http_status=404,
        latency_ms=8.0,
        correlation_id="corr-legal-bad",
        error_message=(
            "Legal tag 'opendes-open-test' not found in partition "
            "'example-opendes'."
        ),
    )


def _ok_submit_result() -> WorkflowRunResult:
    return WorkflowRunResult(
        workflow_id="wf-1",
        run_id="run-42",
        status=WorkflowStatus.IN_PROGRESS,
        raw_status="submitted",
        message=None,
        ok=True,
        http_status=200,
        latency_ms=33.5,
        correlation_id="corr-submit",
        error_message=None,
        raw_response={"runId": "run-42", "status": "submitted"},
    )


def _failed_submit_result() -> WorkflowRunResult:
    return WorkflowRunResult(
        workflow_id=None,
        run_id=None,
        status=WorkflowStatus.UNKNOWN,
        raw_status="",
        message=None,
        ok=False,
        http_status=500,
        latency_ms=20.0,
        correlation_id="corr-submit-bad",
        error_message="Workflow exploded.",
        raw_response={"message": "Workflow exploded."},
    )


def _poll_result(
    status: WorkflowStatus,
    *,
    raw_status: str | None = None,
    ok: bool = True,
    http_status: int | None = 200,
    error_message: str | None = None,
) -> WorkflowRunResult:
    return WorkflowRunResult(
        workflow_id="wf-1",
        run_id="run-42",
        status=status,
        raw_status=raw_status if raw_status is not None else status.value,
        message=None,
        ok=ok,
        http_status=http_status,
        latency_ms=12.0,
        correlation_id="corr-poll",
        error_message=error_message,
        raw_response={"runId": "run-42", "status": status.value},
    )


def _search_result(kind: str, count: int, *, ok: bool = True) -> SearchResult:
    return SearchResult(
        kind=kind,
        count=count,
        records=[{"id": f"{kind}-{i}"} for i in range(count)],
        ok=ok,
        http_status=200 if ok else 500,
        latency_ms=14.0,
        correlation_id=f"corr-search-{kind[:6]}",
        error_message=None if ok else "boom",
    )


# ---------------------------------------------------------------------------
# Service-call spy helper
# ---------------------------------------------------------------------------


class _Spy:
    """Aggregates calls to every patched service function."""

    def __init__(self) -> None:
        self.legal: list[tuple[Any, str, str]] = []
        self.submit: list[tuple[Any, str, dict]] = []
        self.poll: list[tuple[Any, str, str]] = []
        self.search: list[tuple[Any, str, str]] = []
        self.token: list[Any] = []
        self.sleep: list[float] = []


def _patch_services(
    page_module: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    *,
    legal_result: LegalTagCheckResult | None = None,
    submit_result: WorkflowRunResult | None = None,
    poll_results: list[WorkflowRunResult] | None = None,
    search_factory: Any = None,
    token: str | None = "test-token",
) -> _Spy:
    spy = _Spy()
    poll_queue = list(poll_results) if poll_results is not None else []

    def fake_get_token(connection: ADMEConnection, **_: Any) -> str:
        spy.token.append(connection)
        if token is None:
            from app.services.auth import AuthenticationError
            raise AuthenticationError("no token")
        return token

    def fake_check_legal_tag(
        connection: ADMEConnection,
        supplied_token: str,
        legal_tag_name: str,
    ) -> LegalTagCheckResult:
        spy.legal.append((connection, supplied_token, legal_tag_name))
        return legal_result or _ok_legal_result()

    def fake_submit_manifest(
        connection: ADMEConnection,
        supplied_token: str,
        manifest_payload: dict,
    ) -> WorkflowRunResult:
        spy.submit.append((connection, supplied_token, manifest_payload))
        return submit_result or _ok_submit_result()

    def fake_get_workflow_status(
        connection: ADMEConnection,
        supplied_token: str,
        run_id: str,
    ) -> WorkflowRunResult:
        spy.poll.append((connection, supplied_token, run_id))
        if poll_queue:
            return poll_queue.pop(0)
        # Default: stay IN_PROGRESS so the active polling state is stable.
        return _poll_result(WorkflowStatus.IN_PROGRESS)

    def fake_search(
        connection: ADMEConnection,
        supplied_token: str,
        kind: str,
    ) -> SearchResult:
        spy.search.append((connection, supplied_token, kind))
        if search_factory is not None:
            result = search_factory(kind)
            assert isinstance(result, SearchResult)
            return result
        return _search_result(kind, 1)

    monkeypatch.setattr(page_module, "get_token", fake_get_token)
    monkeypatch.setattr(page_module, "check_legal_tag", fake_check_legal_tag)
    monkeypatch.setattr(page_module, "submit_manifest", fake_submit_manifest)
    monkeypatch.setattr(
        page_module, "get_workflow_status", fake_get_workflow_status
    )
    monkeypatch.setattr(
        page_module, "search_records_by_kind", fake_search
    )

    def fake_sleep(seconds: float) -> None:
        spy.sleep.append(seconds)

    monkeypatch.setattr(page_module.time, "sleep", fake_sleep)
    return spy


# ===========================================================================
# Pre-flight guards (LOCKED — never fire any service call when blocked)
# ===========================================================================


def test_page_blocks_when_no_connection_configured(
    streamlit_recorder: StreamlitRecorder,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    page_module = _load_ingestion_module(streamlit_recorder, monkeypatch)
    spy = _patch_services(page_module, monkeypatch)

    page_module.main()

    info_messages = [
        call.args[0] for call in streamlit_recorder.calls_named("info")
    ]
    assert any("Instance Configuration" in m for m in info_messages)
    assert streamlit_recorder.calls_named("page_link"), (
        "must link operators back to Instance Configuration"
    )
    assert spy.legal == []
    assert spy.submit == []
    assert spy.poll == []
    assert spy.search == []


def test_page_blocks_user_impersonation_without_token(
    streamlit_recorder: StreamlitRecorder,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    streamlit_recorder.session_state[CONNECTION_KEY] = _user_connection()
    streamlit_recorder.session_state[USER_AUTH_STATE_KEY] = None
    page_module = _load_ingestion_module(streamlit_recorder, monkeypatch)
    spy = _patch_services(page_module, monkeypatch)

    page_module.main()

    info_messages = [
        call.args[0] for call in streamlit_recorder.calls_named("info")
    ]
    assert any("Instance Configuration" in m for m in info_messages)
    assert streamlit_recorder.calls_named("page_link")
    assert spy.legal == []
    assert spy.submit == []


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
    page_module = _load_ingestion_module(streamlit_recorder, monkeypatch)
    spy = _patch_services(page_module, monkeypatch)

    page_module.main()

    assert streamlit_recorder.calls_named("page_link"), (
        "must point operators back to Instance Configuration"
    )
    assert spy.legal == []
    assert spy.submit == []


# ===========================================================================
# TNO sample insertion
# ===========================================================================


def test_insert_tno_sample_button_populates_manifest_textarea_with_raw_template(
    streamlit_recorder: StreamlitRecorder,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Click 'Insert TNO sample' → ``MANIFEST_TEXT_KEY`` gets the raw template
    (placeholders intact, NOT yet substituted)."""
    streamlit_recorder.session_state[CONNECTION_KEY] = (
        _service_principal_connection()
    )
    streamlit_recorder.button_responses[INSERT_SAMPLE_LABEL] = True
    page_module = _load_ingestion_module(streamlit_recorder, monkeypatch)
    _patch_services(page_module, monkeypatch)

    page_module.main()

    raw = streamlit_recorder.session_state[MANIFEST_TEXT_KEY]
    assert isinstance(raw, str)
    assert raw == page_module.TNO_SAMPLE_MANIFEST
    # Placeholders remain — substitution only happens at submit time.
    assert "{{LEGAL_TAG_NAME}}" in raw
    assert "{{ACL_OWNERS}}" in raw
    assert "{{ACL_VIEWERS}}" in raw
    assert "{{DATA_PARTITION_ID}}" in raw


# ===========================================================================
# Submit pipeline — pre-flight branches
# ===========================================================================


def test_submit_pipeline_with_invalid_json_aborts_at_step_1(
    streamlit_recorder: StreamlitRecorder,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    streamlit_recorder.session_state[CONNECTION_KEY] = (
        _service_principal_connection()
    )
    streamlit_recorder.session_state[MANIFEST_TEXT_KEY] = "{not json"
    streamlit_recorder.session_state[LEGAL_TAG_KEY] = "opendes-tag"
    streamlit_recorder.session_state[ACL_OWNERS_KEY] = "owners@x"
    streamlit_recorder.session_state[ACL_VIEWERS_KEY] = "viewers@x"
    streamlit_recorder.button_responses[VALIDATE_LABEL] = True
    page_module = _load_ingestion_module(streamlit_recorder, monkeypatch)
    spy = _patch_services(page_module, monkeypatch)

    page_module.main()

    error_messages = [
        call.args[0] for call in streamlit_recorder.calls_named("error")
    ]
    assert any("not valid" in m or "valid JSON" in m for m in error_messages)
    assert spy.legal == []
    assert spy.submit == []
    assert streamlit_recorder.session_state[RUN_ID_KEY] is None


def test_submit_pipeline_with_missing_legal_tag_inputs_aborts_at_step_1(
    streamlit_recorder: StreamlitRecorder,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    streamlit_recorder.session_state[CONNECTION_KEY] = (
        _service_principal_connection()
    )
    streamlit_recorder.session_state[MANIFEST_TEXT_KEY] = VALID_MANIFEST_TEXT
    streamlit_recorder.session_state[LEGAL_TAG_KEY] = ""
    streamlit_recorder.session_state[ACL_OWNERS_KEY] = ""
    streamlit_recorder.session_state[ACL_VIEWERS_KEY] = ""
    streamlit_recorder.button_responses[VALIDATE_LABEL] = True
    page_module = _load_ingestion_module(streamlit_recorder, monkeypatch)
    spy = _patch_services(page_module, monkeypatch)

    page_module.main()

    error_messages = [
        call.args[0] for call in streamlit_recorder.calls_named("error")
    ]
    # Pre-pipeline gate lists each missing field by name; pipeline never runs.
    assert any(
        "fill in" in m.lower() and "legal tag" in m.lower()
        for m in error_messages
    )
    assert any("ACL owners" in m for m in error_messages)
    assert any("ACL viewers" in m for m in error_messages)
    assert spy.legal == []
    assert spy.submit == []
    # The sticky error key is set so the message survives reruns.
    assert streamlit_recorder.session_state.get(
        "ingestion_last_error"
    ) is not None


# ===========================================================================
# Submit pipeline — placeholder substitution chains validate → substitute → validate
# ===========================================================================


def test_submit_pipeline_with_placeholders_substitutes_then_revalidates(
    streamlit_recorder: StreamlitRecorder,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Manifest containing ``{{`` triggers substitute → validate → submit."""
    streamlit_recorder.session_state[CONNECTION_KEY] = (
        _service_principal_connection()
    )
    streamlit_recorder.session_state[MANIFEST_TEXT_KEY] = (
        '{"executionContext": {"manifest": {"ReferenceData": '
        '[{"kind": "{{LEGAL_TAG_NAME}}-kind"}]}}}'
    )
    streamlit_recorder.session_state[LEGAL_TAG_KEY] = "tag-1"
    streamlit_recorder.session_state[ACL_OWNERS_KEY] = "owners@x"
    streamlit_recorder.session_state[ACL_VIEWERS_KEY] = "viewers@x"
    streamlit_recorder.button_responses[VALIDATE_LABEL] = True
    page_module = _load_ingestion_module(streamlit_recorder, monkeypatch)
    spy = _patch_services(page_module, monkeypatch)

    page_module.main()

    # legal-tag check ran with the substituted (cleaned) tag value.
    assert spy.legal, "legal-tag check must fire after successful substitution"
    assert spy.legal[0][2] == "tag-1"
    # Manifest text in session is the substituted version (no `{{` markers).
    final_text = streamlit_recorder.session_state[MANIFEST_TEXT_KEY]
    assert isinstance(final_text, str)
    assert "{{" not in final_text
    assert "tag-1-kind" in final_text


# ===========================================================================
# Submit pipeline — legal-tag failure short-circuits submit
# ===========================================================================


def test_legal_tag_failure_renders_status_and_does_not_call_submit(
    streamlit_recorder: StreamlitRecorder,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    streamlit_recorder.session_state[CONNECTION_KEY] = (
        _service_principal_connection()
    )
    streamlit_recorder.session_state[MANIFEST_TEXT_KEY] = VALID_MANIFEST_TEXT
    streamlit_recorder.session_state[LEGAL_TAG_KEY] = "missing-tag"
    streamlit_recorder.session_state[ACL_OWNERS_KEY] = "owners@x"
    streamlit_recorder.session_state[ACL_VIEWERS_KEY] = "viewers@x"
    streamlit_recorder.button_responses[VALIDATE_LABEL] = True
    page_module = _load_ingestion_module(streamlit_recorder, monkeypatch)
    spy = _patch_services(
        page_module, monkeypatch, legal_result=_failed_legal_result()
    )

    page_module.main()

    error_messages = [
        call.args[0] for call in streamlit_recorder.calls_named("error")
    ]
    combined = "\n".join(error_messages)
    assert "Legal tag" in combined or "not found" in combined.lower()
    assert "404" in combined
    assert "corr-legal-bad" in combined
    assert "Hint" in combined or "create" in combined.lower()
    # submit_manifest MUST NOT fire after legal tag failure.
    assert spy.submit == []
    # History has exactly one entry (the legal-tag check).
    history = streamlit_recorder.session_state[HISTORY_KEY]
    assert isinstance(history, list)
    assert len(history) == 1
    assert history[0]["endpoint"] == "legal-tag-check"
    assert history[0]["ok"] is False


# ===========================================================================
# Submit pipeline — submit failure renders error + raw response, no polling
# ===========================================================================


def test_submit_failure_renders_error_and_does_not_start_polling(
    streamlit_recorder: StreamlitRecorder,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    streamlit_recorder.session_state[CONNECTION_KEY] = (
        _service_principal_connection()
    )
    streamlit_recorder.session_state[MANIFEST_TEXT_KEY] = VALID_MANIFEST_TEXT
    streamlit_recorder.session_state[LEGAL_TAG_KEY] = "tag-1"
    streamlit_recorder.session_state[ACL_OWNERS_KEY] = "owners@x"
    streamlit_recorder.session_state[ACL_VIEWERS_KEY] = "viewers@x"
    streamlit_recorder.button_responses[VALIDATE_LABEL] = True
    page_module = _load_ingestion_module(streamlit_recorder, monkeypatch)
    spy = _patch_services(
        page_module, monkeypatch, submit_result=_failed_submit_result()
    )

    page_module.main()

    error_messages = [
        call.args[0] for call in streamlit_recorder.calls_named("error")
    ]
    combined = "\n".join(error_messages)
    assert "Workflow exploded" in combined
    assert "500" in combined
    # Raw response expander rendered.
    expanders = streamlit_recorder.calls_named("expander")
    assert any(
        call.args and "Raw response" in call.args[0] for call in expanders
    ), "submit failure must surface a Raw response expander"
    # Polling state was NOT set up.
    assert streamlit_recorder.session_state[RUN_ID_KEY] is None
    assert streamlit_recorder.session_state[POLLING_ACTIVE_KEY] is False
    assert spy.poll == []


# ===========================================================================
# Submit pipeline — happy path persists run_id, submit_started_at, kinds
# ===========================================================================


def test_submit_success_persists_run_id_started_at_and_kinds(
    streamlit_recorder: StreamlitRecorder,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    streamlit_recorder.session_state[CONNECTION_KEY] = (
        _service_principal_connection()
    )
    streamlit_recorder.session_state[MANIFEST_TEXT_KEY] = VALID_MANIFEST_TEXT
    streamlit_recorder.session_state[LEGAL_TAG_KEY] = "tag-1"
    streamlit_recorder.session_state[ACL_OWNERS_KEY] = "owners@x"
    streamlit_recorder.session_state[ACL_VIEWERS_KEY] = "viewers@x"
    streamlit_recorder.button_responses[VALIDATE_LABEL] = True
    page_module = _load_ingestion_module(streamlit_recorder, monkeypatch)
    spy = _patch_services(page_module, monkeypatch)

    page_module.main()

    # submit fired exactly once with a dict payload that contains executionContext.
    assert len(spy.submit) == 1
    assert "executionContext" in spy.submit[0][2]
    # Locked session-state keys populated.
    assert streamlit_recorder.session_state[RUN_ID_KEY] == "run-42"
    started_at = streamlit_recorder.session_state[SUBMIT_STARTED_AT_KEY]
    assert isinstance(started_at, datetime)
    assert streamlit_recorder.session_state[KINDS_KEY] == [KIND_A]
    assert streamlit_recorder.session_state[POLLING_ACTIVE_KEY] is True


# ===========================================================================
# Polling — single in-progress poll
# ===========================================================================


def _seed_active_run(
    streamlit_recorder: StreamlitRecorder,
    *,
    elapsed_seconds: float = 5.0,
    kinds: list[str] | None = None,
    polling_active: bool = True,
    workflow_status: WorkflowStatus | None = WorkflowStatus.IN_PROGRESS,
) -> None:
    streamlit_recorder.session_state[CONNECTION_KEY] = (
        _service_principal_connection()
    )
    streamlit_recorder.session_state[RUN_ID_KEY] = "run-42"
    streamlit_recorder.session_state[SUBMIT_STARTED_AT_KEY] = datetime.now(
        tz=UTC
    ) - timedelta(seconds=elapsed_seconds)
    streamlit_recorder.session_state[KINDS_KEY] = (
        list(kinds) if kinds is not None else [KIND_A]
    )
    streamlit_recorder.session_state[POLLING_ACTIVE_KEY] = polling_active
    streamlit_recorder.session_state[WORKFLOW_STATUS_KEY] = workflow_status


def test_polling_in_progress_keeps_polling_active_and_does_not_verify(
    streamlit_recorder: StreamlitRecorder,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _seed_active_run(streamlit_recorder)
    page_module = _load_ingestion_module(streamlit_recorder, monkeypatch)
    spy = _patch_services(
        page_module,
        monkeypatch,
        poll_results=[_poll_result(WorkflowStatus.IN_PROGRESS)],
    )

    page_module.main()

    assert len(spy.poll) == 1
    assert (
        streamlit_recorder.session_state[WORKFLOW_STATUS_KEY]
        == WorkflowStatus.IN_PROGRESS
    )
    assert streamlit_recorder.session_state[POLLING_ACTIVE_KEY] is True
    # Verification must NOT fire while still in progress.
    assert spy.search == []
    # IN_PROGRESS without manual refresh → page sleeps before rerun.
    assert spy.sleep, "IN_PROGRESS poll should schedule a sleep before rerun"


def test_polling_finished_disables_polling_and_kicks_off_verification(
    streamlit_recorder: StreamlitRecorder,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _seed_active_run(streamlit_recorder)
    page_module = _load_ingestion_module(streamlit_recorder, monkeypatch)
    spy = _patch_services(
        page_module,
        monkeypatch,
        poll_results=[_poll_result(WorkflowStatus.FINISHED)],
        search_factory=lambda kind: _search_result(kind, 1),
    )

    page_module.main()

    assert len(spy.poll) == 1
    assert (
        streamlit_recorder.session_state[WORKFLOW_STATUS_KEY]
        == WorkflowStatus.FINISHED
    )
    assert streamlit_recorder.session_state[POLLING_ACTIVE_KEY] is False
    # The single rerun-in-the-recorder is a no-op, so verification fires
    # AFTER FINISHED in the same render via the FINISHED branch's main()
    # continuation. But because main() already returned via st.rerun() (a
    # no-op here), verification only runs on the NEXT render. Re-render to
    # exercise the verification path.
    page_module.main()

    assert len(spy.search) == 1
    assert spy.search[0][2] == KIND_A
    assert streamlit_recorder.session_state[VERIFICATION_DONE_KEY] is True


def test_polling_failed_disables_polling_renders_error_no_verification(
    streamlit_recorder: StreamlitRecorder,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _seed_active_run(streamlit_recorder)
    page_module = _load_ingestion_module(streamlit_recorder, monkeypatch)
    spy = _patch_services(
        page_module,
        monkeypatch,
        poll_results=[
            _poll_result(
                WorkflowStatus.FAILED,
                ok=False,
                error_message="dag failed",
            )
        ],
    )

    page_module.main()

    assert (
        streamlit_recorder.session_state[WORKFLOW_STATUS_KEY]
        == WorkflowStatus.FAILED
    )
    assert streamlit_recorder.session_state[POLLING_ACTIVE_KEY] is False
    assert spy.search == []
    error_messages = [
        call.args[0] for call in streamlit_recorder.calls_named("error")
    ]
    assert any("failed" in m.lower() for m in error_messages)


def test_manual_refresh_button_forces_a_poll_without_sleeping(
    streamlit_recorder: StreamlitRecorder,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Manual refresh skips the cadence ladder — no time.sleep between polls."""
    _seed_active_run(streamlit_recorder, elapsed_seconds=1.0)
    streamlit_recorder.button_responses[REFRESH_LABEL] = True
    page_module = _load_ingestion_module(streamlit_recorder, monkeypatch)
    spy = _patch_services(
        page_module,
        monkeypatch,
        poll_results=[_poll_result(WorkflowStatus.IN_PROGRESS)],
    )

    page_module.main()

    assert len(spy.poll) == 1
    # Manual refresh path bypasses the cadence-ladder time.sleep.
    assert spy.sleep == [], (
        "manual refresh must not sleep before the next rerun"
    )


# ===========================================================================
# Verification — retry cap on count==0
# ===========================================================================


def test_verification_retries_zero_count_up_to_three_times_then_warns(
    streamlit_recorder: StreamlitRecorder,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """count=0 → up to 3 attempts total (1 initial + 2 retries) with sleep."""
    _seed_active_run(
        streamlit_recorder,
        polling_active=False,
        workflow_status=WorkflowStatus.FINISHED,
    )
    streamlit_recorder.session_state[VERIFICATION_DONE_KEY] = False
    page_module = _load_ingestion_module(streamlit_recorder, monkeypatch)
    spy = _patch_services(
        page_module,
        monkeypatch,
        search_factory=lambda kind: _search_result(kind, 0),
    )

    page_module.main()

    # 3 attempts max per kind (1 initial + 2 retries), 1 kind seeded.
    assert len(spy.search) == 3
    # 2 sleeps between attempts at the locked 5-second cadence.
    assert spy.sleep == [5, 5]
    warnings = [
        call.args[0] for call in streamlit_recorder.calls_named("warning")
    ]
    assert any(
        "caught up" in w.lower() or "search index" in w.lower()
        for w in warnings
    )
    # NOT a red error for delayed indexing.
    error_messages = [
        call.args[0] for call in streamlit_recorder.calls_named("error")
    ]
    assert not any("Verification" in m for m in error_messages)


def test_verification_all_kinds_positive_renders_success(
    streamlit_recorder: StreamlitRecorder,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _seed_active_run(
        streamlit_recorder,
        kinds=[KIND_A, KIND_B],
        polling_active=False,
        workflow_status=WorkflowStatus.FINISHED,
    )
    streamlit_recorder.session_state[VERIFICATION_DONE_KEY] = False
    page_module = _load_ingestion_module(streamlit_recorder, monkeypatch)
    spy = _patch_services(
        page_module,
        monkeypatch,
        search_factory=lambda kind: _search_result(kind, 3),
    )

    page_module.main()

    # One call per kind (no retries needed when count > 0).
    assert len(spy.search) == 2
    assert {call[2] for call in spy.search} == {KIND_A, KIND_B}
    assert spy.sleep == []
    success_messages = [
        call.args[0] for call in streamlit_recorder.calls_named("success")
    ]
    assert any("verified" in m.lower() for m in success_messages)


def test_verification_one_kind_zero_after_retries_renders_warning_not_error(
    streamlit_recorder: StreamlitRecorder,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A single kind=0 after retries must be a yellow warning, not red error."""
    _seed_active_run(
        streamlit_recorder,
        kinds=[KIND_A, KIND_B],
        polling_active=False,
        workflow_status=WorkflowStatus.FINISHED,
    )
    streamlit_recorder.session_state[VERIFICATION_DONE_KEY] = False
    page_module = _load_ingestion_module(streamlit_recorder, monkeypatch)

    def _factory(kind: str) -> SearchResult:
        return _search_result(kind, 5 if kind == KIND_A else 0)

    spy = _patch_services(page_module, monkeypatch, search_factory=_factory)

    page_module.main()

    # KIND_A: 1 call, count=5; KIND_B: 3 retries, count=0 → 4 total search calls.
    assert len(spy.search) == 4
    # 2 retry sleeps for KIND_B only.
    assert spy.sleep == [5, 5]
    warnings = [
        call.args[0] for call in streamlit_recorder.calls_named("warning")
    ]
    assert any(
        "caught up" in w.lower() or "search index" in w.lower()
        for w in warnings
    )
    # NO red error from verification.
    error_messages = [
        call.args[0] for call in streamlit_recorder.calls_named("error")
    ]
    assert not any("Verification" in m for m in error_messages)


def test_failed_workflow_skips_verification_entirely(
    streamlit_recorder: StreamlitRecorder,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _seed_active_run(
        streamlit_recorder,
        polling_active=False,
        workflow_status=WorkflowStatus.FAILED,
    )
    page_module = _load_ingestion_module(streamlit_recorder, monkeypatch)
    spy = _patch_services(page_module, monkeypatch)

    page_module.main()

    assert spy.search == []
    assert spy.sleep == []


# ===========================================================================
# History — one row per HTTP call, correct labels, clear-history persists
# ===========================================================================


def test_full_pipeline_history_has_one_row_per_call_with_contract_labels(
    streamlit_recorder: StreamlitRecorder,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Submit pipeline + 1 poll + 2 searches → 4 history rows with contract
    endpoint labels."""
    streamlit_recorder.session_state[CONNECTION_KEY] = (
        _service_principal_connection()
    )
    streamlit_recorder.session_state[MANIFEST_TEXT_KEY] = (
        VALID_MANIFEST_TWO_SECTIONS_TEXT
    )
    streamlit_recorder.session_state[LEGAL_TAG_KEY] = "tag-1"
    streamlit_recorder.session_state[ACL_OWNERS_KEY] = "owners@x"
    streamlit_recorder.session_state[ACL_VIEWERS_KEY] = "viewers@x"
    streamlit_recorder.button_responses[VALIDATE_LABEL] = True
    page_module = _load_ingestion_module(streamlit_recorder, monkeypatch)
    _patch_services(
        page_module,
        monkeypatch,
        poll_results=[_poll_result(WorkflowStatus.IN_PROGRESS)],
    )

    page_module.main()

    history = streamlit_recorder.session_state[HISTORY_KEY]
    assert isinstance(history, list)
    endpoints = [row["endpoint"] for row in history]
    # legal-tag check + submit + 1 poll (in-progress) — verification not yet.
    assert endpoints == ["legal-tag-check", "submit", "poll"]
    assert all("timestamp" in row for row in history)
    assert all("latency_ms" in row for row in history)
    assert all("ok" in row for row in history)


def test_history_records_search_calls_with_per_kind_labels(
    streamlit_recorder: StreamlitRecorder,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _seed_active_run(
        streamlit_recorder,
        kinds=[KIND_A, KIND_B],
        polling_active=False,
        workflow_status=WorkflowStatus.FINISHED,
    )
    streamlit_recorder.session_state[VERIFICATION_DONE_KEY] = False
    page_module = _load_ingestion_module(streamlit_recorder, monkeypatch)
    _patch_services(
        page_module,
        monkeypatch,
        search_factory=lambda kind: _search_result(kind, 1),
    )

    page_module.main()

    history = streamlit_recorder.session_state[HISTORY_KEY]
    assert isinstance(history, list)
    endpoints = [row["endpoint"] for row in history]
    assert f"search.{KIND_A}" in endpoints
    assert f"search.{KIND_B}" in endpoints


def test_clear_history_button_empties_history_and_persists_across_rerun(
    streamlit_recorder: StreamlitRecorder,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    streamlit_recorder.session_state[CONNECTION_KEY] = (
        _service_principal_connection()
    )
    streamlit_recorder.session_state[HISTORY_KEY] = [
        {
            "timestamp": "2026-05-06T10:30:00Z",
            "endpoint": "legal-tag-check",
            "ok": True,
            "http_status": 200,
            "latency_ms": 10.0,
            "correlation_id": "c1",
            "error_message": None,
        }
    ]
    streamlit_recorder.button_responses[CLEAR_HISTORY_TOP_LABEL] = True
    page_module = _load_ingestion_module(streamlit_recorder, monkeypatch)
    _patch_services(page_module, monkeypatch)

    page_module.main()

    assert streamlit_recorder.session_state[HISTORY_KEY] == []

    # Survives a rerun: clear the button-response, render again — history
    # stays empty and a no-history caption appears.
    streamlit_recorder.button_responses[CLEAR_HISTORY_TOP_LABEL] = False
    streamlit_recorder.calls.clear()
    page_module.main()

    assert streamlit_recorder.session_state[HISTORY_KEY] == []
    captions = [
        call.args[0] for call in streamlit_recorder.calls_named("caption")
    ]
    assert any("No ingestion API calls" in c for c in captions)
