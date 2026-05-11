"""Tests for the ADME file-upload page (``app/pages/6_📂_File_Upload.py``).

Mirrors the ingestion-page test pattern: load the script via importlib
with a ``StreamlitRecorder`` substituted for ``streamlit``, seed session
state, drive widget answers, and assert on recorded calls + state.
"""

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
from app.models.osdu import (
    FileMetadataResult,
    LegalTagListResult,
    UploadBytesResult,
    UploadURLResult,
)
from tests.support.streamlit_recorder import StreamlitRecorder

FILE_UPLOAD_PAGE_PATH = (
    Path(__file__).resolve().parents[1]
    / "app"
    / "pages"
    / "6_📂_File_Upload.py"
)

# Locked session keys (per Satya's contract — Charlie tests these names).
FILE_UPLOAD_LEGAL_TAG_KEY = "file_upload_legal_tag"
FILE_UPLOAD_ACL_OWNERS_KEY = "file_upload_acl_owners"
FILE_UPLOAD_ACL_VIEWERS_KEY = "file_upload_acl_viewers"
FILE_UPLOAD_DISPLAY_NAME_KEY = "file_upload_display_name"
FILE_UPLOAD_DESCRIPTION_KEY = "file_upload_description"
FILE_UPLOAD_LAST_RESULT_KEY = "file_upload_last_result"
FILE_UPLOAD_HISTORY_KEY = "file_upload_history"
FILE_UPLOAD_LAST_ERROR_KEY = "file_upload_last_error"
FILE_UPLOAD_AUTORUN_KEY = "file_upload_autorun_done"
FILE_UPLOAD_LEGAL_TAG_OPTIONS_KEY = "file_upload_legal_tag_options"
FILE_UPLOAD_ACL_OWNER_OPTIONS_KEY = "file_upload_acl_owner_options"
FILE_UPLOAD_ACL_VIEWER_OPTIONS_KEY = "file_upload_acl_viewer_options"

ALL_LOCKED_KEYS = (
    FILE_UPLOAD_LEGAL_TAG_KEY,
    FILE_UPLOAD_ACL_OWNERS_KEY,
    FILE_UPLOAD_ACL_VIEWERS_KEY,
    FILE_UPLOAD_DISPLAY_NAME_KEY,
    FILE_UPLOAD_DESCRIPTION_KEY,
    FILE_UPLOAD_LAST_RESULT_KEY,
    FILE_UPLOAD_HISTORY_KEY,
    FILE_UPLOAD_LAST_ERROR_KEY,
    FILE_UPLOAD_AUTORUN_KEY,
    FILE_UPLOAD_LEGAL_TAG_OPTIONS_KEY,
    FILE_UPLOAD_ACL_OWNER_OPTIONS_KEY,
    FILE_UPLOAD_ACL_VIEWER_OPTIONS_KEY,
)

FILE_UPLOADER_LABEL = "Choose a file"
SUBMIT_BUTTON_LABEL = "📤 Upload & Register"
UPLOAD_ANOTHER_LABEL = "📤 Upload another"
CLEAR_HISTORY_LABEL = "🧹 Clear history"


# ---------------------------------------------------------------------------
# Module loader
# ---------------------------------------------------------------------------


def _load_page(
    streamlit_recorder: StreamlitRecorder,
    monkeypatch: pytest.MonkeyPatch,
) -> ModuleType:
    monkeypatch.setitem(sys.modules, "streamlit", streamlit_recorder)
    module_name = "tests.generated_file_upload_page"
    sys.modules.pop(module_name, None)
    spec = importlib.util.spec_from_file_location(
        module_name, FILE_UPLOAD_PAGE_PATH
    )
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


# ---------------------------------------------------------------------------
# Test doubles
# ---------------------------------------------------------------------------


class FakeUploadedFile:
    """Minimal stand-in for Streamlit's ``UploadedFile``."""

    def __init__(
        self,
        name: str = "well.las",
        size: int = 1024,
        type_: str = "application/octet-stream",
        content: bytes | None = None,
    ) -> None:
        self.name = name
        self.size = size
        self.type = type_
        self._content = content if content is not None else b"x" * size

    def getvalue(self) -> bytes:
        return self._content


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


# ---------------------------------------------------------------------------
# Service spy
# ---------------------------------------------------------------------------


class _Spy:
    def __init__(self) -> None:
        self.upload_url: list[tuple[Any, str]] = []
        self.upload_bytes: list[tuple[str, bytes, dict[str, Any]]] = []
        self.metadata: list[tuple[Any, str, dict[str, Any]]] = []
        self.token: list[Any] = []


def _patch_services(
    page_module: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    *,
    upload_url_result: UploadURLResult | None = None,
    upload_bytes_result: UploadBytesResult | None = None,
    metadata_result: FileMetadataResult | None = None,
    token: str | None = "test-token",
    legal_tags_ok: bool = False,
    legal_tags_items: list[str] | None = None,
) -> _Spy:
    spy = _Spy()

    def fake_get_token(connection: ADMEConnection, **_: Any) -> str:
        spy.token.append(connection)
        if token is None:
            from app.services.auth import AuthenticationError
            raise AuthenticationError("no token")
        return token

    def fake_get_upload_url(
        connection: ADMEConnection, supplied_token: str
    ) -> UploadURLResult:
        spy.upload_url.append((connection, supplied_token))
        if upload_url_result is not None:
            return upload_url_result
        return UploadURLResult(
            ok=True,
            http_status=200,
            latency_ms=10.0,
            correlation_id="corr-up",
            signed_url="https://blob.example/sas?sig=xyz",
            file_source="/staging/abc",
            file_id="fid-99",
        )

    def fake_upload_file_bytes(
        signed_url: str,
        file_bytes: bytes,
        *,
        content_type: str = "application/octet-stream",
        timeout: int = 120,
    ) -> UploadBytesResult:
        spy.upload_bytes.append(
            (
                signed_url,
                file_bytes,
                {"content_type": content_type, "timeout": timeout},
            )
        )
        if upload_bytes_result is not None:
            return upload_bytes_result
        return UploadBytesResult(
            ok=True,
            http_status=201,
            latency_ms=22.0,
            bytes_uploaded=len(file_bytes),
        )

    def fake_post_file_metadata(
        connection: ADMEConnection,
        supplied_token: str,
        **kwargs: Any,
    ) -> FileMetadataResult:
        spy.metadata.append((connection, supplied_token, kwargs))
        if metadata_result is not None:
            return metadata_result
        return FileMetadataResult(
            ok=True,
            http_status=201,
            latency_ms=33.0,
            correlation_id="corr-md",
            record_id="opendes:dataset--File.Generic:abc",
            record_version=1,
        )

    from app.models.osdu import LegalTag

    items = [
        LegalTag(name=name, description="", properties={})
        for name in (legal_tags_items or [])
    ]

    def fake_list_legal_tags(
        _connection: ADMEConnection,
        _token: str,
        *,
        valid: bool | None = None,
    ) -> LegalTagListResult:
        del valid
        return LegalTagListResult(
            items=items,
            ok=legal_tags_ok,
            http_status=200 if legal_tags_ok else None,
            error_message=None if legal_tags_ok else "stubbed",
        )

    def fake_fetch_groups(
        _connection: ADMEConnection, _token: str
    ) -> EntitlementsCallResult:
        return EntitlementsCallResult(
            endpoint="groups",
            path="/api/entitlements/v2/groups",
            ok=False,
            error_message="stubbed",
        )

    monkeypatch.setattr(page_module, "get_token", fake_get_token)
    monkeypatch.setattr(page_module, "get_upload_url", fake_get_upload_url)
    monkeypatch.setattr(
        page_module, "upload_file_bytes", fake_upload_file_bytes
    )
    monkeypatch.setattr(
        page_module, "post_file_metadata", fake_post_file_metadata
    )
    monkeypatch.setattr(page_module, "list_legal_tags", fake_list_legal_tags)
    monkeypatch.setattr(page_module, "fetch_groups", fake_fetch_groups)
    return spy


def _seed_ready_state(recorder: StreamlitRecorder) -> None:
    """Connection + ACL + legal tag filled, recorder ready to submit."""
    recorder.session_state[CONNECTION_KEY] = (
        _service_principal_connection()
    )
    recorder.session_state[FILE_UPLOAD_LEGAL_TAG_KEY] = "opendes-public"
    recorder.session_state[FILE_UPLOAD_ACL_OWNERS_KEY] = (
        "data.default.owners@opendes.dataservices.energy"
    )
    recorder.session_state[FILE_UPLOAD_ACL_VIEWERS_KEY] = (
        "data.default.viewers@opendes.dataservices.energy"
    )


# ===========================================================================
# Pre-flight guards
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
    page_links = streamlit_recorder.calls_named("page_link")
    assert page_links, "must link operators back to Instance Configuration"
    assert spy.upload_url == []
    assert spy.upload_bytes == []
    assert spy.metadata == []


def test_page_blocks_user_impersonation_without_token(
    streamlit_recorder: StreamlitRecorder,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    streamlit_recorder.session_state[CONNECTION_KEY] = _user_connection()
    streamlit_recorder.session_state[USER_AUTH_STATE_KEY] = None
    page_module = _load_page(streamlit_recorder, monkeypatch)
    spy = _patch_services(page_module, monkeypatch)

    page_module.main()

    info_messages = [
        call.args[0] for call in streamlit_recorder.calls_named("info")
    ]
    assert any("Instance Configuration" in m for m in info_messages)
    assert streamlit_recorder.calls_named("page_link")
    assert spy.upload_url == []


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
    assert spy.upload_url == []


# ===========================================================================
# Session-state defaults — 11 locked keys (12 incl. autorun-done)
# ===========================================================================


def test_all_locked_session_state_keys_initialized_on_first_render(
    streamlit_recorder: StreamlitRecorder,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    streamlit_recorder.session_state[CONNECTION_KEY] = (
        _service_principal_connection()
    )
    page_module = _load_page(streamlit_recorder, monkeypatch)
    _patch_services(page_module, monkeypatch)

    page_module.main()

    for key in ALL_LOCKED_KEYS:
        assert key in streamlit_recorder.session_state, (
            f"locked key {key!r} not initialized"
        )


# ===========================================================================
# Autorun-once option loading
# ===========================================================================


def test_autorun_fires_legal_tags_and_groups_exactly_once(
    streamlit_recorder: StreamlitRecorder,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    streamlit_recorder.session_state[CONNECTION_KEY] = (
        _service_principal_connection()
    )
    page_module = _load_page(streamlit_recorder, monkeypatch)

    calls = {"legal": 0, "groups": 0}

    def counting_list_legal_tags(*_: Any, **__: Any) -> LegalTagListResult:
        calls["legal"] += 1
        return LegalTagListResult(items=[], ok=True)

    def counting_fetch_groups(*_: Any, **__: Any) -> EntitlementsCallResult:
        calls["groups"] += 1
        return EntitlementsCallResult(
            endpoint="groups",
            path="/x",
            ok=False,
            error_message="stub",
        )

    monkeypatch.setattr(page_module, "get_token", lambda *_, **__: "t")
    monkeypatch.setattr(
        page_module, "list_legal_tags", counting_list_legal_tags
    )
    monkeypatch.setattr(page_module, "fetch_groups", counting_fetch_groups)
    monkeypatch.setattr(
        page_module, "get_upload_url", lambda *_, **__: UploadURLResult()
    )
    monkeypatch.setattr(
        page_module,
        "upload_file_bytes",
        lambda *_, **__: UploadBytesResult(),
    )
    monkeypatch.setattr(
        page_module,
        "post_file_metadata",
        lambda *_, **__: FileMetadataResult(),
    )

    # The import-time ``main()`` consumed the autorun flag without our
    # patches in place (real auth raised, the page caught it and set
    # autorun-done=True). Reset so we can observe the patched path.
    streamlit_recorder.session_state[FILE_UPLOAD_AUTORUN_KEY] = False

    # First render fires.
    page_module.main()
    assert calls == {"legal": 1, "groups": 1}

    # Second render does NOT re-fire (autorun-done flag is set).
    page_module.main()
    assert calls == {"legal": 1, "groups": 1}


def test_refresh_button_bypasses_autorun_flag(
    streamlit_recorder: StreamlitRecorder,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    streamlit_recorder.session_state[CONNECTION_KEY] = (
        _service_principal_connection()
    )
    streamlit_recorder.button_responses[
        "🔄 Refresh legal tags & groups"
    ] = True
    page_module = _load_page(streamlit_recorder, monkeypatch)

    calls = {"legal": 0}

    def counting_list_legal_tags(*_: Any, **__: Any) -> LegalTagListResult:
        calls["legal"] += 1
        return LegalTagListResult(items=[], ok=True)

    monkeypatch.setattr(page_module, "get_token", lambda *_, **__: "t")
    monkeypatch.setattr(
        page_module, "list_legal_tags", counting_list_legal_tags
    )
    monkeypatch.setattr(
        page_module,
        "fetch_groups",
        lambda *_, **__: EntitlementsCallResult(
            endpoint="g", path="/x", ok=False, error_message="stub"
        ),
    )
    monkeypatch.setattr(
        page_module, "get_upload_url", lambda *_, **__: UploadURLResult()
    )
    monkeypatch.setattr(
        page_module,
        "upload_file_bytes",
        lambda *_, **__: UploadBytesResult(),
    )
    monkeypatch.setattr(
        page_module,
        "post_file_metadata",
        lambda *_, **__: FileMetadataResult(),
    )

    # Pre-mark autorun as done; refresh-button must still re-fire.
    streamlit_recorder.session_state[FILE_UPLOAD_AUTORUN_KEY] = True

    page_module.main()
    assert calls["legal"] == 1, (
        "Refresh button must force list_legal_tags even when autorun-done"
    )


def test_autorun_failure_falls_back_to_text_inputs_with_warning_caption(
    streamlit_recorder: StreamlitRecorder,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    streamlit_recorder.session_state[CONNECTION_KEY] = (
        _service_principal_connection()
    )
    page_module = _load_page(streamlit_recorder, monkeypatch)
    _patch_services(page_module, monkeypatch, legal_tags_ok=False)

    page_module.main()

    # Legal tag field rendered as text_input (selectbox fallback).
    text_input_labels = [
        call.args[0]
        for call in streamlit_recorder.calls_named("text_input")
    ]
    assert "Legal tag" in text_input_labels
    assert "ACL owners group" in text_input_labels
    assert "ACL viewers group" in text_input_labels

    # Warning captions present.
    caption_messages = [
        call.args[0] if call.args else ""
        for call in streamlit_recorder.calls_named("caption")
    ]
    combined = "\n".join(caption_messages)
    assert "Couldn't load legal tags" in combined
    assert "Couldn't load groups" in combined


# ===========================================================================
# File selection gates
# ===========================================================================


def test_no_file_selected_submit_does_not_run_pipeline(
    streamlit_recorder: StreamlitRecorder,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _seed_ready_state(streamlit_recorder)
    streamlit_recorder.button_responses[SUBMIT_BUTTON_LABEL] = True
    # No file_uploader_response registered → returns None.
    page_module = _load_page(streamlit_recorder, monkeypatch)
    spy = _patch_services(page_module, monkeypatch)

    page_module.main()

    # Pipeline never began.
    assert spy.upload_url == []
    assert spy.upload_bytes == []
    # Sticky error surfaced.
    error_messages = [
        call.args[0] for call in streamlit_recorder.calls_named("error")
    ]
    assert any("choose a file" in m.lower() for m in error_messages)


def test_file_over_100mb_renders_red_error_and_disables_submit(
    streamlit_recorder: StreamlitRecorder,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _seed_ready_state(streamlit_recorder)
    # 100 MB + 1 byte → over limit.
    streamlit_recorder.file_uploader_responses[FILE_UPLOADER_LABEL] = (
        FakeUploadedFile(
            name="huge.bin", size=100 * 1024 * 1024 + 1, content=b"x"
        )
    )
    streamlit_recorder.button_responses[SUBMIT_BUTTON_LABEL] = True
    page_module = _load_page(streamlit_recorder, monkeypatch)
    spy = _patch_services(page_module, monkeypatch)

    page_module.main()

    error_messages = [
        call.args[0] for call in streamlit_recorder.calls_named("error")
    ]
    assert any("100 MB" in m for m in error_messages)
    # Submit button was rendered with disabled=True.
    submit_buttons = [
        call
        for call in streamlit_recorder.calls_named("button")
        if call.args and call.args[0] == SUBMIT_BUTTON_LABEL
    ]
    assert submit_buttons
    assert submit_buttons[0].kwargs.get("disabled") is True
    # Pipeline did not start.
    assert spy.upload_url == []


@pytest.mark.parametrize(
    "missing_key",
    [
        FILE_UPLOAD_LEGAL_TAG_KEY,
        FILE_UPLOAD_ACL_OWNERS_KEY,
        FILE_UPLOAD_ACL_VIEWERS_KEY,
    ],
)
def test_missing_metadata_field_blocks_pipeline(
    streamlit_recorder: StreamlitRecorder,
    monkeypatch: pytest.MonkeyPatch,
    missing_key: str,
) -> None:
    _seed_ready_state(streamlit_recorder)
    streamlit_recorder.session_state[missing_key] = ""
    streamlit_recorder.file_uploader_responses[FILE_UPLOADER_LABEL] = (
        FakeUploadedFile()
    )
    streamlit_recorder.button_responses[SUBMIT_BUTTON_LABEL] = True
    page_module = _load_page(streamlit_recorder, monkeypatch)
    spy = _patch_services(page_module, monkeypatch)

    page_module.main()

    error_messages = [
        call.args[0] for call in streamlit_recorder.calls_named("error")
    ]
    combined = "\n".join(error_messages)
    assert "fill in" in combined.lower()
    assert spy.upload_url == []
    assert streamlit_recorder.session_state[FILE_UPLOAD_LAST_ERROR_KEY] is not None


# ===========================================================================
# Happy path — 3 phases succeed
# ===========================================================================


def test_happy_path_runs_all_three_phases_and_records_result(
    streamlit_recorder: StreamlitRecorder,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _seed_ready_state(streamlit_recorder)
    streamlit_recorder.file_uploader_responses[FILE_UPLOADER_LABEL] = (
        FakeUploadedFile(
            name="well.las", size=12, type_="text/plain", content=b"hello bytes!"
        )
    )
    streamlit_recorder.button_responses[SUBMIT_BUTTON_LABEL] = True
    page_module = _load_page(streamlit_recorder, monkeypatch)
    spy = _patch_services(page_module, monkeypatch)

    page_module.main()

    assert len(spy.upload_url) == 1
    assert len(spy.upload_bytes) == 1
    assert len(spy.metadata) == 1

    # Phase 2 forwarded the signed URL + bytes + content_type.
    signed_url, file_bytes, kwargs = spy.upload_bytes[0]
    assert signed_url == "https://blob.example/sas?sig=xyz"
    assert file_bytes == b"hello bytes!"
    assert kwargs["content_type"] == "text/plain"

    # Phase 3 metadata kwargs.
    _, _, md_kwargs = spy.metadata[0]
    assert md_kwargs["file_source"] == "/staging/abc"
    assert md_kwargs["display_name"] == "well.las"
    assert md_kwargs["legal_tag"] == "opendes-public"

    # Locked result key populated.
    result = streamlit_recorder.session_state[FILE_UPLOAD_LAST_RESULT_KEY]
    assert isinstance(result, FileMetadataResult)
    assert result.ok is True
    assert result.record_id == "opendes:dataset--File.Generic:abc"

    # History has 3 entries.
    history = streamlit_recorder.session_state[FILE_UPLOAD_HISTORY_KEY]
    assert isinstance(history, list)
    assert len(history) == 3
    assert [row["endpoint"] for row in history] == [
        "upload-url",
        "upload-bytes",
        "metadata",
    ]
    assert all(row["ok"] for row in history)


# ===========================================================================
# Phase 1 failure — uploadURL 401
# ===========================================================================


def test_phase1_failure_sets_sticky_error_no_put_attempted(
    streamlit_recorder: StreamlitRecorder,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _seed_ready_state(streamlit_recorder)
    streamlit_recorder.file_uploader_responses[FILE_UPLOADER_LABEL] = (
        FakeUploadedFile()
    )
    streamlit_recorder.button_responses[SUBMIT_BUTTON_LABEL] = True
    page_module = _load_page(streamlit_recorder, monkeypatch)
    spy = _patch_services(
        page_module,
        monkeypatch,
        upload_url_result=UploadURLResult(
            ok=False,
            http_status=401,
            latency_ms=5.0,
            correlation_id="corr-401",
            error_message="Unauthorized",
        ),
    )

    page_module.main()

    assert len(spy.upload_url) == 1
    assert spy.upload_bytes == []
    assert spy.metadata == []
    # Sticky error pinned.
    sticky = streamlit_recorder.session_state[FILE_UPLOAD_LAST_ERROR_KEY]
    assert sticky is not None
    assert "Unauthorized" in sticky or "401" in sticky
    # History has exactly 1 entry (the failed upload-url).
    history = streamlit_recorder.session_state[FILE_UPLOAD_HISTORY_KEY]
    assert len(history) == 1
    assert history[0]["endpoint"] == "upload-url"
    assert history[0]["ok"] is False


# ===========================================================================
# Phase 2 failure — PUT timeout
# ===========================================================================


def test_phase2_failure_sticky_error_mentions_file_id(
    streamlit_recorder: StreamlitRecorder,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _seed_ready_state(streamlit_recorder)
    streamlit_recorder.file_uploader_responses[FILE_UPLOADER_LABEL] = (
        FakeUploadedFile()
    )
    streamlit_recorder.button_responses[SUBMIT_BUTTON_LABEL] = True
    page_module = _load_page(streamlit_recorder, monkeypatch)
    spy = _patch_services(
        page_module,
        monkeypatch,
        upload_bytes_result=UploadBytesResult(
            ok=False,
            http_status=None,
            latency_ms=120000.0,
            error_message="Request timed out after 120s",
            bytes_uploaded=0,
        ),
    )

    page_module.main()

    assert len(spy.upload_url) == 1
    assert len(spy.upload_bytes) == 1
    assert spy.metadata == [], "metadata POST must not fire when PUT failed"

    sticky = streamlit_recorder.session_state[FILE_UPLOAD_LAST_ERROR_KEY]
    assert sticky is not None
    # File id from Phase 1 is mentioned for recovery.
    assert "fid-99" in sticky
    assert "timed out" in sticky.lower()


# ===========================================================================
# Phase 3 failure — metadata 400
# ===========================================================================


def test_phase3_failure_sticky_error_mentions_file_id_and_warns_unregistered(
    streamlit_recorder: StreamlitRecorder,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _seed_ready_state(streamlit_recorder)
    streamlit_recorder.file_uploader_responses[FILE_UPLOADER_LABEL] = (
        FakeUploadedFile()
    )
    streamlit_recorder.button_responses[SUBMIT_BUTTON_LABEL] = True
    page_module = _load_page(streamlit_recorder, monkeypatch)
    spy = _patch_services(
        page_module,
        monkeypatch,
        metadata_result=FileMetadataResult(
            ok=False,
            http_status=400,
            correlation_id="corr-md-bad",
            error_message="Legal tag invalid",
        ),
    )

    page_module.main()

    assert len(spy.upload_url) == 1
    assert len(spy.upload_bytes) == 1
    assert len(spy.metadata) == 1

    sticky = streamlit_recorder.session_state[FILE_UPLOAD_LAST_ERROR_KEY]
    assert sticky is not None
    assert "fid-99" in sticky
    # The operator-recovery warning hints at unregistered file.
    assert "uploaded" in sticky.lower()
    assert "metadata" in sticky.lower()


# ===========================================================================
# Widget mutation safety — display_name/description set BEFORE submit
# ===========================================================================


def test_widget_mutation_safety_when_display_name_preset_before_submit(
    streamlit_recorder: StreamlitRecorder,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Display name + description set in session_state before render → pipeline
    runs without Streamlit's 'cannot modify widget after render' error.

    The page snapshots widget-bound values into locals BEFORE the pipeline
    writes anywhere; this test verifies the snapshot path works.
    """
    _seed_ready_state(streamlit_recorder)
    streamlit_recorder.session_state[FILE_UPLOAD_DISPLAY_NAME_KEY] = (
        "preset-name.las"
    )
    streamlit_recorder.session_state[FILE_UPLOAD_DESCRIPTION_KEY] = (
        "preset description"
    )
    streamlit_recorder.file_uploader_responses[FILE_UPLOADER_LABEL] = (
        FakeUploadedFile(name="file-on-disk.las")
    )
    streamlit_recorder.button_responses[SUBMIT_BUTTON_LABEL] = True
    page_module = _load_page(streamlit_recorder, monkeypatch)
    spy = _patch_services(page_module, monkeypatch)

    page_module.main()  # No exception raised → snapshot pattern works.

    # Pipeline ran with the preset values, not the filename.
    assert len(spy.metadata) == 1
    _, _, md_kwargs = spy.metadata[0]
    assert md_kwargs["display_name"] == "preset-name.las"
    assert md_kwargs["description"] == "preset description"


# ===========================================================================
# Upload another button — clears the right keys
# ===========================================================================


def test_upload_another_clears_result_and_per_file_keys_only(
    streamlit_recorder: StreamlitRecorder,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _seed_ready_state(streamlit_recorder)
    streamlit_recorder.session_state[FILE_UPLOAD_LAST_RESULT_KEY] = (
        FileMetadataResult(
            ok=True,
            http_status=201,
            record_id="opendes:dataset--File.Generic:abc",
            record_version=1,
        )
    )
    streamlit_recorder.session_state[FILE_UPLOAD_DISPLAY_NAME_KEY] = "x.las"
    streamlit_recorder.session_state[FILE_UPLOAD_DESCRIPTION_KEY] = "desc"
    streamlit_recorder.button_responses[UPLOAD_ANOTHER_LABEL] = True
    page_module = _load_page(streamlit_recorder, monkeypatch)
    _patch_services(page_module, monkeypatch)

    page_module.main()

    # Cleared.
    assert streamlit_recorder.session_state[FILE_UPLOAD_LAST_RESULT_KEY] is None
    assert streamlit_recorder.session_state[FILE_UPLOAD_DISPLAY_NAME_KEY] == ""
    assert streamlit_recorder.session_state[FILE_UPLOAD_DESCRIPTION_KEY] == ""
    # NOT cleared — operator wants to upload another with same metadata.
    assert (
        streamlit_recorder.session_state[FILE_UPLOAD_LEGAL_TAG_KEY]
        == "opendes-public"
    )
    assert streamlit_recorder.session_state[FILE_UPLOAD_ACL_OWNERS_KEY] != ""
    assert streamlit_recorder.session_state[FILE_UPLOAD_ACL_VIEWERS_KEY] != ""


# ===========================================================================
# View in Search — page link
# ===========================================================================


def test_view_in_search_page_link_target(
    streamlit_recorder: StreamlitRecorder,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _seed_ready_state(streamlit_recorder)
    streamlit_recorder.session_state[FILE_UPLOAD_LAST_RESULT_KEY] = (
        FileMetadataResult(
            ok=True,
            http_status=201,
            record_id="opendes:dataset--File.Generic:abc",
            record_version=1,
        )
    )
    page_module = _load_page(streamlit_recorder, monkeypatch)
    _patch_services(page_module, monkeypatch)

    page_module.main()

    page_link_targets = [
        call.args[0] if call.args else ""
        for call in streamlit_recorder.calls_named("page_link")
    ]
    assert any(
        "5_🔍_Search.py" in target for target in page_link_targets
    ), f"View in Search page_link missing; got {page_link_targets!r}"


# ===========================================================================
# History clear button
# ===========================================================================


def test_clear_history_empties_history_key(
    streamlit_recorder: StreamlitRecorder,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _seed_ready_state(streamlit_recorder)
    streamlit_recorder.session_state[FILE_UPLOAD_HISTORY_KEY] = [
        {
            "timestamp": "2026-05-11T00:00:00Z",
            "endpoint": "upload-url",
            "ok": True,
            "http_status": 200,
            "latency_ms": 10.0,
            "correlation_id": "c",
            "error_message": None,
        }
    ]
    streamlit_recorder.button_responses[CLEAR_HISTORY_LABEL] = True
    page_module = _load_page(streamlit_recorder, monkeypatch)
    _patch_services(page_module, monkeypatch)

    page_module.main()

    assert streamlit_recorder.session_state[FILE_UPLOAD_HISTORY_KEY] == []
