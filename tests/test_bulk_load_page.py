"""Tests for the Bulk Load page (`app/pages/9_📥_Bulk_Load.py`)."""

from __future__ import annotations

import importlib.util
import sys
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

from app.connection_state import CONNECTION_KEY
from app.models.connection import ADMEConnection, AuthMethod
from app.models.osdu import (
    DatasetDescriptor,
    DatasetTier,
    ManifestPreview,
    SubmitResult,
)
from tests.support.streamlit_recorder import StreamlitRecorder

BULK_LOAD_PAGE_PATH = (
    Path(__file__).resolve().parents[1]
    / "app"
    / "pages"
    / "9_📥_Bulk_Load.py"
)

# Locked session keys.
DATASET_KEY = "bulk_dataset_id"
TIER_KEY = "bulk_tier"
LEGAL_TAG_KEY = "bulk_legal_tag"
ACL_OWNERS_KEY = "bulk_acl_owners"
ACL_VIEWERS_KEY = "bulk_acl_viewers"
PREVIEW_SEEN_KEY = "bulk_preview_seen"
PREVIEW_RESULTS_KEY = "bulk_preview_results"
SUBMIT_RESULTS_KEY = "bulk_submit_results"
LAST_ERROR_KEY = "bulk_last_error"

# Internal helper keys (autorun-once option load).
OPTIONS_AUTORUN_KEY = "bulk_options_autorun_done"
LEGAL_TAG_OPTIONS_KEY = "bulk_legal_tag_options"
OWNER_OPTIONS_KEY = "bulk_acl_owner_options"
VIEWER_OPTIONS_KEY = "bulk_acl_viewer_options"

PREVIEW_LABEL = "🔍 Preview manifests"
SUBMIT_LABEL = "🚀 Submit all manifests"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _connection() -> ADMEConnection:
    return ADMEConnection(
        endpoint="https://example.energy.azure.com",
        tenant_id="11111111-1111-1111-1111-111111111111",
        client_id="22222222-2222-2222-2222-222222222222",
        data_partition_id="example-opendes",
        auth_method=AuthMethod.SERVICE_PRINCIPAL,
        client_secret="placeholder-secret",
    )


def _tno_descriptor(tmp_path: Path) -> DatasetDescriptor:
    root = tmp_path / "datasets" / "tno"
    root.mkdir(parents=True, exist_ok=True)
    (root / "NOTICE.md").write_text("# TNO Notice\nApache-2.0", encoding="utf-8")
    return DatasetDescriptor(
        id="tno",
        display_name="TNO Open Test Data",
        source_url="https://community.opengroup.org/osdu/data/open-test-data",
        notice_path="NOTICE.md",
        tiers={
            "reference-data": DatasetTier(
                enabled=True,
                manifest_glob="*.json",
                description="13 reference-data tables",
            ),
            "master-data": DatasetTier(
                enabled=False, reason="v2 — not yet vendored"
            ),
            "work-products": DatasetTier(
                enabled=False, reason="v2 — not yet vendored"
            ),
        },
        root_dir=root,
    )


def _volve_descriptor(tmp_path: Path) -> DatasetDescriptor:
    root = tmp_path / "datasets" / "volve"
    root.mkdir(parents=True, exist_ok=True)
    return DatasetDescriptor(
        id="volve",
        display_name="Volve Open Dataset",
        source_url="https://example.com/volve",
        notice_path="NOTICE.md",
        tiers={
            "reference-data": DatasetTier(
                enabled=False, reason="not yet vendored"
            ),
        },
        root_dir=root,
    )


def _preview_row(filename: str, kind: str, count: int) -> ManifestPreview:
    return ManifestPreview(
        path=Path(filename),
        filename=filename,
        kind=kind,
        record_count=count,
        record_section="ReferenceData",
    )


def _submit_row(
    filename: str, *, ok: bool, run_id: str | None = None, error: str | None = None
) -> SubmitResult:
    return SubmitResult(
        manifest_path=Path(filename),
        filename=filename,
        status="success" if ok else "error",
        run_id=run_id,
        record_id=None,
        error=error,
        submitted_at=datetime.now(UTC),
    )


def _load_page(
    streamlit_recorder: StreamlitRecorder,
    monkeypatch: pytest.MonkeyPatch,
) -> ModuleType:
    monkeypatch.setitem(sys.modules, "streamlit", streamlit_recorder)
    module_name = "tests.generated_bulk_load_page"
    sys.modules.pop(module_name, None)
    spec = importlib.util.spec_from_file_location(
        module_name, BULK_LOAD_PAGE_PATH
    )
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _patch_service(
    page_module: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    *,
    datasets: list[DatasetDescriptor] | None = None,
    preview_result: list[ManifestPreview] | None = None,
    preview_raises: Exception | None = None,
    submit_results: list[SubmitResult] | None = None,
    submit_raises: Exception | None = None,
) -> dict[str, list[Any]]:
    """Patch bulk_loader + auth + dropdown loaders. Returns a call-spy dict."""
    spy: dict[str, list[Any]] = {
        "list": [],
        "preview": [],
        "submit": [],
        "tokens": [],
    }

    def fake_list_datasets() -> list[DatasetDescriptor]:
        spy["list"].append(True)
        return list(datasets or [])

    def fake_preview_tier(
        dataset_id: str, tier: str
    ) -> list[ManifestPreview]:
        spy["preview"].append((dataset_id, tier))
        if preview_raises is not None:
            raise preview_raises
        return list(preview_result or [])

    def fake_submit_tier(
        dataset_id: str,
        tier: str,
        **kwargs: Any,
    ) -> Iterator[SubmitResult]:
        spy["submit"].append((dataset_id, tier, kwargs))
        if submit_raises is not None:
            raise submit_raises
        yield from list(submit_results or [])

    def fake_get_token(connection: ADMEConnection, **_: Any) -> str:
        spy["tokens"].append(connection)
        return "test-token"

    def fake_clear_cache() -> None:
        return None

    monkeypatch.setattr(page_module, "list_datasets", fake_list_datasets)
    monkeypatch.setattr(page_module, "preview_tier", fake_preview_tier)
    monkeypatch.setattr(page_module, "submit_tier", fake_submit_tier)
    monkeypatch.setattr(page_module, "get_token", fake_get_token)
    monkeypatch.setattr(page_module, "_clear_cache", fake_clear_cache)

    # Stub legal-tag + groups loaders so the autorun-once option load
    # cannot make real HTTP calls. Returning ok=False causes the page to
    # fall back to st.text_input for each field, which is what the tests
    # drive via session_state writes.
    from app.models.connection import EntitlementsCallResult
    from app.models.osdu import LegalTagListResult

    def fake_list_legal_tags(
        _c: ADMEConnection, _t: str, *, valid: bool | None = None
    ) -> LegalTagListResult:
        del valid
        return LegalTagListResult(
            items=[], ok=False, error_message="stubbed in tests"
        )

    def fake_fetch_groups(
        _c: ADMEConnection, _t: str
    ) -> EntitlementsCallResult:
        return EntitlementsCallResult(
            endpoint="groups",
            path="/api/entitlements/v2/groups",
            ok=False,
            http_status=None,
            latency_ms=0.0,
            correlation_id=None,
            error_message="stubbed in tests",
            raw_response=None,
            data=None,
        )

    monkeypatch.setattr(page_module, "list_legal_tags", fake_list_legal_tags)
    monkeypatch.setattr(page_module, "fetch_groups", fake_fetch_groups)
    return spy


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_page_renders_without_crashing_on_clean_session(
    streamlit_recorder: StreamlitRecorder,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A session with no connection should preflight-info, not crash."""
    page_module = _load_page(streamlit_recorder, monkeypatch)
    spy = _patch_service(page_module, monkeypatch)

    page_module.main()

    info_messages = [
        call.args[0] for call in streamlit_recorder.calls_named("info")
    ]
    assert any("Instance Configuration" in m for m in info_messages)
    assert streamlit_recorder.calls_named("page_link")
    # Preflight blocks BEFORE list_datasets is called.
    assert spy["list"] == []
    assert spy["preview"] == []
    assert spy["submit"] == []


def test_dataset_selector_populates_from_list_datasets(
    streamlit_recorder: StreamlitRecorder,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    streamlit_recorder.session_state[CONNECTION_KEY] = _connection()
    page_module = _load_page(streamlit_recorder, monkeypatch)
    tno = _tno_descriptor(tmp_path)
    volve = _volve_descriptor(tmp_path)
    spy = _patch_service(page_module, monkeypatch, datasets=[tno, volve])

    page_module.main()

    assert spy["list"], "list_datasets was not called"
    # Dataset selectbox renders with both ids as options.
    dataset_select = [
        call
        for call in streamlit_recorder.calls_named("selectbox")
        if call.args and call.args[0] == "Dataset"
    ]
    assert dataset_select, "Dataset selectbox was not rendered"
    options = dataset_select[0].args[1]
    assert list(options) == ["tno", "volve"]


def test_selecting_tno_shows_source_url(
    streamlit_recorder: StreamlitRecorder,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    streamlit_recorder.session_state[CONNECTION_KEY] = _connection()
    streamlit_recorder.session_state[DATASET_KEY] = "tno"
    page_module = _load_page(streamlit_recorder, monkeypatch)
    tno = _tno_descriptor(tmp_path)
    # Make _read_notice succeed by pointing DATA_ROOT at the tmp tree.
    monkeypatch.setattr(page_module, "DATA_ROOT", tmp_path.resolve())
    _patch_service(page_module, monkeypatch, datasets=[tno])

    page_module.main()

    markdown_args = [
        call.args[0] for call in streamlit_recorder.calls_named("markdown")
    ]
    assert any(tno.source_url in m for m in markdown_args), (
        "Source URL must appear in the Source & license expander"
    )


def test_tier_selector_filters_to_enabled_and_lists_disabled(
    streamlit_recorder: StreamlitRecorder,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    streamlit_recorder.session_state[CONNECTION_KEY] = _connection()
    streamlit_recorder.session_state[DATASET_KEY] = "tno"
    page_module = _load_page(streamlit_recorder, monkeypatch)
    tno = _tno_descriptor(tmp_path)
    _patch_service(page_module, monkeypatch, datasets=[tno])

    page_module.main()

    tier_radios = [
        call
        for call in streamlit_recorder.calls_named("radio")
        if call.args and call.args[0] == "Tier"
    ]
    assert tier_radios, "Tier radio was not rendered"
    options = list(tier_radios[0].args[1])
    assert options == ["reference-data"], (
        "Only enabled tiers should appear in the radio"
    )

    info_messages = [
        call.args[0] for call in streamlit_recorder.calls_named("info")
    ]
    assert any(
        "master-data" in m and "work-products" in m for m in info_messages
    ), "Disabled tiers must be surfaced in an info block"


def test_submit_button_disabled_before_preview(
    streamlit_recorder: StreamlitRecorder,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    streamlit_recorder.session_state[CONNECTION_KEY] = _connection()
    streamlit_recorder.session_state[DATASET_KEY] = "tno"
    streamlit_recorder.session_state[TIER_KEY] = "reference-data"
    # Even with legal+ACL filled, no preview yet => Submit disabled.
    streamlit_recorder.session_state[LEGAL_TAG_KEY] = "opendes-tno-data"
    streamlit_recorder.session_state[ACL_OWNERS_KEY] = "data.x.owners@x"
    streamlit_recorder.session_state[ACL_VIEWERS_KEY] = "data.x.viewers@x"
    page_module = _load_page(streamlit_recorder, monkeypatch)
    tno = _tno_descriptor(tmp_path)
    _patch_service(page_module, monkeypatch, datasets=[tno])

    page_module.main()

    submit_buttons = [
        call
        for call in streamlit_recorder.calls_named("button")
        if call.args and call.args[0] == SUBMIT_LABEL
    ]
    assert submit_buttons, "Submit button must be rendered"
    assert submit_buttons[0].kwargs.get("disabled") is True, (
        "Submit must be disabled before Preview"
    )

    captions = [
        call.args[0] for call in streamlit_recorder.calls_named("caption")
    ]
    assert any("Run Preview first" in c for c in captions), (
        "Disabled-reason caption must explain the Preview gate"
    )


def test_clicking_preview_enables_submit_when_form_complete(
    streamlit_recorder: StreamlitRecorder,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    streamlit_recorder.session_state[CONNECTION_KEY] = _connection()
    streamlit_recorder.session_state[DATASET_KEY] = "tno"
    streamlit_recorder.session_state[TIER_KEY] = "reference-data"
    streamlit_recorder.session_state[LEGAL_TAG_KEY] = "opendes-tno-data"
    streamlit_recorder.session_state[ACL_OWNERS_KEY] = "data.x.owners@x"
    streamlit_recorder.session_state[ACL_VIEWERS_KEY] = "data.x.viewers@x"
    # Simulate operator already having clicked Preview on a prior run by
    # priming the gate flag + cached preview rows. The current render
    # should therefore enable Submit.
    streamlit_recorder.session_state[PREVIEW_SEEN_KEY] = (
        "tno",
        "reference-data",
    )
    streamlit_recorder.session_state[PREVIEW_RESULTS_KEY] = [
        _preview_row("load_a.json", "osdu:wks:reference-data--A:1.0.0", 12),
        _preview_row("load_b.json", "osdu:wks:reference-data--B:1.0.0", 8),
    ]
    page_module = _load_page(streamlit_recorder, monkeypatch)
    tno = _tno_descriptor(tmp_path)
    _patch_service(page_module, monkeypatch, datasets=[tno])

    page_module.main()

    submit_buttons = [
        call
        for call in streamlit_recorder.calls_named("button")
        if call.args and call.args[0] == SUBMIT_LABEL
    ]
    assert submit_buttons
    assert submit_buttons[0].kwargs.get("disabled") is False, (
        "Submit must enable once Preview has been seen and form is complete"
    )

    # Preview summary line + dataframe should render.
    success_args = [
        call.args[0] for call in streamlit_recorder.calls_named("success")
    ]
    assert any("2 manifests" in s and "20" in s for s in success_args), (
        "Preview summary line must show count + total records"
    )
    assert streamlit_recorder.calls_named("dataframe"), (
        "Preview table must render"
    )


def test_submit_disabled_when_legal_tag_empty(
    streamlit_recorder: StreamlitRecorder,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    streamlit_recorder.session_state[CONNECTION_KEY] = _connection()
    streamlit_recorder.session_state[DATASET_KEY] = "tno"
    streamlit_recorder.session_state[TIER_KEY] = "reference-data"
    streamlit_recorder.session_state[LEGAL_TAG_KEY] = ""  # empty
    streamlit_recorder.session_state[ACL_OWNERS_KEY] = "data.x.owners@x"
    streamlit_recorder.session_state[ACL_VIEWERS_KEY] = "data.x.viewers@x"
    streamlit_recorder.session_state[PREVIEW_SEEN_KEY] = (
        "tno",
        "reference-data",
    )
    streamlit_recorder.session_state[PREVIEW_RESULTS_KEY] = [
        _preview_row("load_a.json", "kindA", 1),
    ]
    page_module = _load_page(streamlit_recorder, monkeypatch)
    tno = _tno_descriptor(tmp_path)
    _patch_service(page_module, monkeypatch, datasets=[tno])

    page_module.main()

    submit_buttons = [
        call
        for call in streamlit_recorder.calls_named("button")
        if call.args and call.args[0] == SUBMIT_LABEL
    ]
    assert submit_buttons
    assert submit_buttons[0].kwargs.get("disabled") is True

    captions = [
        call.args[0] for call in streamlit_recorder.calls_named("caption")
    ]
    assert any("legal tag" in c.lower() for c in captions)


def test_preview_invalidates_when_dataset_changes(
    streamlit_recorder: StreamlitRecorder,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Changing dataset wipes the preview gate so Submit re-locks."""
    streamlit_recorder.session_state[CONNECTION_KEY] = _connection()
    # Operator previously previewed TNO. Now they pick VOLVE — but volve
    # has no enabled tiers, so the test focuses on the gate-clearing
    # behavior alone: starting with a stale seen-key, the page resets it.
    streamlit_recorder.session_state[DATASET_KEY] = "tno"
    streamlit_recorder.session_state[TIER_KEY] = "reference-data"
    streamlit_recorder.session_state[PREVIEW_SEEN_KEY] = (
        "volve",
        "reference-data",
    )
    streamlit_recorder.session_state[PREVIEW_RESULTS_KEY] = [
        _preview_row("stale.json", "kind", 1),
    ]
    page_module = _load_page(streamlit_recorder, monkeypatch)
    tno = _tno_descriptor(tmp_path)
    _patch_service(page_module, monkeypatch, datasets=[tno])

    page_module.main()

    # The gate must be cleared because the selected dataset is "tno"
    # but the seen key was ("volve", "reference-data").
    assert streamlit_recorder.session_state[PREVIEW_SEEN_KEY] is None
    assert streamlit_recorder.session_state[PREVIEW_RESULTS_KEY] == []


def test_submit_renders_mixed_success_and_failure_results(
    streamlit_recorder: StreamlitRecorder,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Clicking Submit iterates submit_tier and renders ✅/❌ rows."""
    streamlit_recorder.session_state[CONNECTION_KEY] = _connection()
    streamlit_recorder.session_state[DATASET_KEY] = "tno"
    streamlit_recorder.session_state[TIER_KEY] = "reference-data"
    streamlit_recorder.session_state[LEGAL_TAG_KEY] = "opendes-tno-data"
    streamlit_recorder.session_state[ACL_OWNERS_KEY] = "data.x.owners@x"
    streamlit_recorder.session_state[ACL_VIEWERS_KEY] = "data.x.viewers@x"
    streamlit_recorder.session_state[PREVIEW_SEEN_KEY] = (
        "tno",
        "reference-data",
    )
    streamlit_recorder.session_state[PREVIEW_RESULTS_KEY] = [
        _preview_row("load_a.json", "kindA", 1),
        _preview_row("load_b.json", "kindB", 1),
    ]
    streamlit_recorder.button_responses[SUBMIT_LABEL] = True

    page_module = _load_page(streamlit_recorder, monkeypatch)
    tno = _tno_descriptor(tmp_path)
    spy = _patch_service(
        page_module,
        monkeypatch,
        datasets=[tno],
        submit_results=[
            _submit_row("load_a.json", ok=True, run_id="run-1"),
            _submit_row("load_b.json", ok=False, error="boom"),
        ],
    )

    page_module.main()

    assert spy["submit"], "submit_tier should have been called"
    submit_call = spy["submit"][0]
    assert submit_call[0] == "tno"
    assert submit_call[1] == "reference-data"
    kwargs = submit_call[2]
    assert kwargs["acl_owners"] == ["data.x.owners@x"]
    assert kwargs["acl_viewers"] == ["data.x.viewers@x"]
    assert kwargs["legal_tag"] == "opendes-tno-data"
    assert kwargs["data_partition_id"] == "example-opendes"

    # Streamed per-row markdown for each result.
    markdown_args = [
        call.args[0] for call in streamlit_recorder.calls_named("markdown")
    ]
    assert any(
        "✅" in m and "load_a.json" in m and "run-1" in m for m in markdown_args
    )
    assert any(
        "❌" in m and "load_b.json" in m and "boom" in m for m in markdown_args
    )

    # Persistent summary banner — 1 of 2 succeeded → st.warning.
    warning_args = [
        call.args[0] for call in streamlit_recorder.calls_named("warning")
    ]
    assert any(
        "1 of 2 succeeded" in w and "1 failed" in w for w in warning_args
    )

    # Submit results stored for re-render on next rerun.
    stored = streamlit_recorder.session_state[SUBMIT_RESULTS_KEY]
    assert len(stored) == 2
    assert stored[0].status == "success"
    assert stored[1].status == "error"
