"""File-upload page for ADME.

Drives the canonical OSDU File Service v2 three-call upload flow:
signed URL → PUT bytes to Azure Blob → metadata POST. Mirrors the
ingestion page's pre-flight chain, sticky-error pattern, autorun-once
option loading, history dataframe, and latency line chart.
"""

from __future__ import annotations

import mimetypes
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if PROJECT_ROOT not in {Path(path or ".").resolve() for path in sys.path}:
    sys.path.insert(0, str(PROJECT_ROOT))

import pandas as pd  # type: ignore[import-untyped]  # noqa: E402
import streamlit as st  # type: ignore[import-not-found]  # noqa: E402

from app.connection_state import (  # noqa: E402
    ensure_session_defaults,
    get_connection,
    get_user_auth_state,
)
from app.models.connection import (  # noqa: E402
    ADMEConnection,
    AuthMethod,
)
from app.models.osdu import (  # noqa: E402
    FileMetadataResult,
    UploadBytesResult,
    UploadURLResult,
)
from app.services.auth import AuthenticationError, get_token  # noqa: E402
from app.services.entitlements import fetch_groups  # noqa: E402
from app.services.files import (  # noqa: E402
    MAX_FILE_BYTES_V1,
    get_upload_url,
    post_file_metadata,
    upload_file_bytes,
)
from app.services.legal_tags import list_legal_tags  # noqa: E402

SETTINGS_PAGE_PATH = "pages/1_⚙️_Instance_Configuration.py"
SEARCH_PAGE_PATH = "pages/5_🔍_Search.py"

# --- Locked session-state keys (per Satya's contract) --------------------
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

# Streamlit-managed; do NOT lock or write to this key.
FILE_UPLOAD_UPLOADER_WIDGET_KEY = "file_upload_uploader_widget"

HISTORY_DISPLAY_LIMIT = 20

# Endpoint labels for the in-session history.
LABEL_UPLOAD_URL = "upload-url"
LABEL_UPLOAD_BYTES = "upload-bytes"
LABEL_METADATA = "metadata"


class _PipelineFailureError(Exception):
    """Short-circuit the upload pipeline with a sticky-error summary."""


def main() -> None:
    """Render the file upload page."""
    st.set_page_config(
        page_title="File Upload · ADME Control Plane",
        page_icon="📂",
        layout="wide",
    )
    st.title("📂 Upload a file to ADME")
    st.markdown(
        "Upload a single file to your ADME instance via the OSDU File "
        "Service v2 three-step flow: request a signed URL, push the bytes "
        "to Azure Blob Storage, then register the file metadata. Returns "
        "a record id you can reference from an ingestion manifest or open "
        "in Search."
    )

    ensure_session_defaults(st.session_state)
    _ensure_page_defaults()

    connection = get_connection(st.session_state)
    if not _preflight_ok(connection):
        return
    assert connection is not None  # mypy — _preflight_ok guarantees this

    st.caption(
        f"Data partition: `{connection.data_partition_id}` · "
        f"Endpoint: `{connection.endpoint}`"
    )

    _render_sticky_error()
    _render_refresh_button(connection)
    _load_input_options(connection)

    uploaded_file = _render_step_1_select_file()
    _render_step_2_metadata()
    _render_step_3_submit(connection, uploaded_file)
    _render_result_panel()
    _render_history()


# ---------------------------------------------------------------------------
# Session bootstrap
# ---------------------------------------------------------------------------


def _ensure_page_defaults() -> None:
    """Initialize page-scoped session keys."""
    st.session_state.setdefault(FILE_UPLOAD_LEGAL_TAG_KEY, "")
    st.session_state.setdefault(FILE_UPLOAD_ACL_OWNERS_KEY, "")
    st.session_state.setdefault(FILE_UPLOAD_ACL_VIEWERS_KEY, "")
    st.session_state.setdefault(FILE_UPLOAD_DISPLAY_NAME_KEY, "")
    st.session_state.setdefault(FILE_UPLOAD_DESCRIPTION_KEY, "")
    st.session_state.setdefault(FILE_UPLOAD_LAST_RESULT_KEY, None)
    st.session_state.setdefault(FILE_UPLOAD_HISTORY_KEY, [])
    st.session_state.setdefault(FILE_UPLOAD_LAST_ERROR_KEY, None)

    st.session_state.setdefault(FILE_UPLOAD_AUTORUN_KEY, False)
    st.session_state.setdefault(FILE_UPLOAD_LEGAL_TAG_OPTIONS_KEY, None)
    st.session_state.setdefault(FILE_UPLOAD_ACL_OWNER_OPTIONS_KEY, None)
    st.session_state.setdefault(FILE_UPLOAD_ACL_VIEWER_OPTIONS_KEY, None)


# ---------------------------------------------------------------------------
# Pre-flight
# ---------------------------------------------------------------------------


def _preflight_ok(connection: ADMEConnection | None) -> bool:
    """Return True when we have everything required to upload."""
    if connection is None or not connection.is_valid():
        st.info(
            "No ADME connection is configured for this session. "
            "Open Instance Configuration to add your endpoint, identity "
            "details, and data partition."
        )
        st.page_link(
            SETTINGS_PAGE_PATH,
            label="Open Instance Configuration",
            icon="⚙️",
        )
        return False

    if connection.auth_method == AuthMethod.USER_IMPERSONATION:
        if get_user_auth_state(st.session_state) is None:
            st.info(
                "No token available for this session. Sign in on the "
                "Instance Configuration page to enable file uploads."
            )
            st.page_link(
                SETTINGS_PAGE_PATH,
                label="Open Instance Configuration",
                icon="⚙️",
            )
            return False

    if not connection.data_partition_id.strip():
        st.info(
            "No data partition is configured for this connection. "
            "Open Instance Configuration to add the OSDU data-partition id."
        )
        st.page_link(
            SETTINGS_PAGE_PATH,
            label="Open Instance Configuration",
            icon="⚙️",
        )
        return False

    return True


def _acquire_token(connection: ADMEConnection) -> str | None:
    """Acquire an ADME token, rendering an operator-safe error on failure."""
    try:
        if connection.auth_method == AuthMethod.USER_IMPERSONATION:
            return get_token(
                connection,
                user_auth_state=get_user_auth_state(st.session_state),
            )
        return get_token(connection)
    except AuthenticationError as exc:
        st.error(
            f"Could not acquire an ADME token: {exc}. "
            "Open Instance Configuration to sign in again or update "
            "credentials."
        )
        st.page_link(
            SETTINGS_PAGE_PATH,
            label="Open Instance Configuration",
            icon="⚙️",
        )
        return None
    except Exception as exc:  # noqa: BLE001 - never leak auth-library internals
        st.error(
            f"Unexpected error acquiring an ADME token: {type(exc).__name__}. "
            "Open Instance Configuration to verify your connection."
        )
        st.page_link(
            SETTINGS_PAGE_PATH,
            label="Open Instance Configuration",
            icon="⚙️",
        )
        return None


# ---------------------------------------------------------------------------
# Sticky error
# ---------------------------------------------------------------------------


def _render_sticky_error() -> None:
    """Render the persistent error banner (if any) above the form."""
    message = st.session_state.get(FILE_UPLOAD_LAST_ERROR_KEY)
    if not message:
        return
    cols = st.columns([8, 1])
    with cols[0]:
        st.error(message)
    with cols[1]:
        if st.button("Dismiss error", key="file_upload_dismiss_error"):
            st.session_state[FILE_UPLOAD_LAST_ERROR_KEY] = None
            st.rerun()


# ---------------------------------------------------------------------------
# Autorun option loading
# ---------------------------------------------------------------------------


def _render_refresh_button(connection: ADMEConnection) -> None:
    """Render the refresh button for legal-tag / group caches."""
    if st.button(
        "🔄 Refresh legal tags & groups",
        key="file_upload_refresh_options",
        help="Re-fetch legal tags and entitlement groups from ADME.",
    ):
        _load_input_options(connection, force=True)
        st.rerun()


def _load_input_options(
    connection: ADMEConnection, *, force: bool = False
) -> None:
    """Autorun-once load of legal tags + entitlement groups for dropdowns."""
    if not force and st.session_state.get(FILE_UPLOAD_AUTORUN_KEY, False):
        return

    token = _acquire_token(connection)
    if token is None:
        st.session_state[FILE_UPLOAD_AUTORUN_KEY] = True
        return

    try:
        with st.spinner("Loading legal tags & groups…"):
            legal_result = list_legal_tags(connection, token, valid=True)
            groups_result = fetch_groups(connection, token)

        if legal_result.ok and legal_result.items:
            names = sorted(
                {tag.name for tag in legal_result.items if tag.name}
            )
            st.session_state[FILE_UPLOAD_LEGAL_TAG_OPTIONS_KEY] = (
                names or None
            )
        else:
            st.session_state[FILE_UPLOAD_LEGAL_TAG_OPTIONS_KEY] = None

        owners, viewers = _partition_acl_groups(groups_result)
        st.session_state[FILE_UPLOAD_ACL_OWNER_OPTIONS_KEY] = (
            owners or None
        )
        st.session_state[FILE_UPLOAD_ACL_VIEWER_OPTIONS_KEY] = (
            viewers or None
        )
    except Exception:  # noqa: BLE001 - never block the page on a load failure
        st.session_state[FILE_UPLOAD_LEGAL_TAG_OPTIONS_KEY] = None
        st.session_state[FILE_UPLOAD_ACL_OWNER_OPTIONS_KEY] = None
        st.session_state[FILE_UPLOAD_ACL_VIEWER_OPTIONS_KEY] = None

    st.session_state[FILE_UPLOAD_AUTORUN_KEY] = True


def _partition_acl_groups(groups_result: Any) -> tuple[list[str], list[str]]:
    """Split a fetch_groups result into sorted owner / viewer email lists."""
    if not getattr(groups_result, "ok", False):
        return [], []
    data = getattr(groups_result, "data", None)
    if not isinstance(data, dict):
        return [], []
    raw_groups = data.get("groups")
    if not isinstance(raw_groups, list):
        return [], []

    owners: set[str] = set()
    viewers: set[str] = set()
    for group in raw_groups:
        if not isinstance(group, dict):
            continue
        email = group.get("email")
        if not isinstance(email, str) or "@" not in email:
            continue
        local = email.split("@", 1)[0]
        if not local.startswith("data."):
            continue
        if local.endswith(".owners"):
            owners.add(email)
        elif local.endswith(".viewers"):
            viewers.add(email)
    return sorted(owners), sorted(viewers)


# ---------------------------------------------------------------------------
# Step 1 — select file
# ---------------------------------------------------------------------------


def _render_step_1_select_file() -> Any:
    """Render the file uploader + file info caption block."""
    st.subheader("Step 1 — Select a file")
    uploaded_file = st.file_uploader(
        "Choose a file",
        type=None,
        accept_multiple_files=False,
        key=FILE_UPLOAD_UPLOADER_WIDGET_KEY,
    )

    if uploaded_file is None:
        return None

    size_bytes = int(getattr(uploaded_file, "size", 0) or 0)
    mime_type = getattr(uploaded_file, "type", None) or "unknown"
    st.caption(
        f"📄 **{uploaded_file.name}** · {_humanize_bytes(size_bytes)} · "
        f"MIME `{mime_type}`"
    )

    if size_bytes > MAX_FILE_BYTES_V1:
        st.error(
            "❌ Files larger than 100 MB aren't supported in this version "
            "— use Azure Storage Explorer for now and register the "
            "FileSource via the API directly."
        )

    return uploaded_file


# ---------------------------------------------------------------------------
# Step 2 — metadata inputs
# ---------------------------------------------------------------------------


def _render_step_2_metadata() -> None:
    """Render legal-tag / ACL selectboxes and the display-name / description."""
    st.subheader("Step 2 — Metadata")

    legal_options = st.session_state.get(FILE_UPLOAD_LEGAL_TAG_OPTIONS_KEY)
    owner_options = st.session_state.get(FILE_UPLOAD_ACL_OWNER_OPTIONS_KEY)
    viewer_options = st.session_state.get(FILE_UPLOAD_ACL_VIEWER_OPTIONS_KEY)

    cols = st.columns(3)
    with cols[0]:
        _render_option_field(
            label="Legal tag",
            session_key=FILE_UPLOAD_LEGAL_TAG_KEY,
            options=legal_options,
            placeholder="opendes-tno-data",
            help_text=(
                "Fully qualified legal tag name applied to the new file "
                "record."
            ),
            empty_caption="⚠️ Couldn't load legal tags — enter manually",
        )
    with cols[1]:
        _render_option_field(
            label="ACL owners group",
            session_key=FILE_UPLOAD_ACL_OWNERS_KEY,
            options=owner_options,
            placeholder="data.default.owners@opendes.dataservices.energy",
            help_text=(
                "Email of the entitlements group that should own this "
                "file record."
            ),
            empty_caption="⚠️ Couldn't load groups — enter manually",
        )
    with cols[2]:
        _render_option_field(
            label="ACL viewers group",
            session_key=FILE_UPLOAD_ACL_VIEWERS_KEY,
            options=viewer_options,
            placeholder="data.default.viewers@opendes.dataservices.energy",
            help_text=(
                "Email of the entitlements group allowed to read this "
                "file record."
            ),
            empty_caption="⚠️ Couldn't load groups — enter manually",
        )

    st.text_input(
        "Display name",
        key=FILE_UPLOAD_DISPLAY_NAME_KEY,
        help="Defaults to the filename if left blank.",
    )
    st.text_area(
        "Description (optional)",
        key=FILE_UPLOAD_DESCRIPTION_KEY,
        height=80,
    )


def _render_option_field(
    *,
    label: str,
    session_key: str,
    options: list[str] | None,
    placeholder: str,
    help_text: str,
    empty_caption: str,
) -> None:
    """Render a selectbox when options loaded; otherwise a text_input."""
    if not options:
        st.text_input(
            label,
            key=session_key,
            placeholder=placeholder,
            help=help_text,
        )
        st.caption(empty_caption)
        return

    current = str(st.session_state.get(session_key) or "")
    final_options: list[str] = [""] + list(options)
    if current and current not in final_options:
        final_options.append(current)
    st.selectbox(
        label,
        options=final_options,
        key=session_key,
        help=help_text,
    )


# ---------------------------------------------------------------------------
# Step 3 — submit + pipeline
# ---------------------------------------------------------------------------


def _render_step_3_submit(
    connection: ADMEConnection, uploaded_file: Any
) -> None:
    """Render the submit button and trigger the upload pipeline on click."""
    st.subheader("Step 3 — Upload & register")

    size_bytes = (
        int(getattr(uploaded_file, "size", 0) or 0)
        if uploaded_file is not None
        else 0
    )
    over_limit = size_bytes > MAX_FILE_BYTES_V1

    if st.button(
        "📤 Upload & Register",
        type="primary",
        key="file_upload_submit_button",
        disabled=over_limit,
    ):
        if uploaded_file is None:
            _set_sticky_error(
                "❌ Cannot upload yet — please choose a file in Step 1."
            )
            return
        if over_limit:
            # Defensive — the button is disabled in this state.
            return
        _run_upload_pipeline(connection, uploaded_file)


def _run_upload_pipeline(
    connection: ADMEConnection, uploaded_file: Any
) -> None:
    """Execute the get-URL → PUT bytes → POST metadata flow on click.

    Snapshots widget-bound display name and description into locals BEFORE
    the pipeline runs so subsequent reads use the resolved values without
    mutating any widget key after the widget rendered.
    """
    # Clear any sticky error from a prior attempt.
    st.session_state[FILE_UPLOAD_LAST_ERROR_KEY] = None

    legal_tag = str(
        st.session_state.get(FILE_UPLOAD_LEGAL_TAG_KEY) or ""
    ).strip()
    acl_owners = str(
        st.session_state.get(FILE_UPLOAD_ACL_OWNERS_KEY) or ""
    ).strip()
    acl_viewers = str(
        st.session_state.get(FILE_UPLOAD_ACL_VIEWERS_KEY) or ""
    ).strip()
    # Snapshot widget-bound values BEFORE the pipeline writes anywhere.
    resolved_display_name = (
        str(st.session_state.get(FILE_UPLOAD_DISPLAY_NAME_KEY) or "").strip()
        or uploaded_file.name
    )
    resolved_description = str(
        st.session_state.get(FILE_UPLOAD_DESCRIPTION_KEY) or ""
    ).strip()

    # ---------- Pre-pipeline gate ---------------------------------------
    missing: list[str] = []
    if not legal_tag:
        missing.append("Legal tag")
    if not acl_owners:
        missing.append("ACL owners group")
    if not acl_viewers:
        missing.append("ACL viewers group")
    if missing:
        bullets = "\n".join(f"- {field}" for field in missing)
        msg = f"❌ Cannot upload yet — please fill in:\n{bullets}"
        _set_sticky_error(msg)
        return

    size_bytes = int(getattr(uploaded_file, "size", 0) or 0)
    if size_bytes <= 0:
        _set_sticky_error(
            "❌ The selected file is empty. Choose a file with content."
        )
        return
    if size_bytes > MAX_FILE_BYTES_V1:
        _set_sticky_error(
            "❌ Files larger than 100 MB aren't supported in this version."
        )
        return

    # Read bytes BEFORE opening the status box so a read failure surfaces
    # on the page rather than flashing inside an auto-collapsing status.
    try:
        file_bytes = uploaded_file.getvalue()
    except Exception as exc:  # noqa: BLE001 - defensive boundary
        _set_sticky_error(
            f"❌ Could not read file bytes: {type(exc).__name__}: {exc}"
        )
        return

    content_type = (
        getattr(uploaded_file, "type", None)
        or _guess_mime(uploaded_file.name)
        or "application/octet-stream"
    )

    token = _acquire_token(connection)
    if token is None:
        _set_sticky_error(
            "❌ Could not acquire an ADME token. Open Instance "
            "Configuration to sign in again or update credentials."
        )
        return

    status_box = st.status("Uploading file…", expanded=True)

    try:
        with status_box:
            # ---------- Phase 1: signed URL -----------------------------
            st.write("**1. Requesting signed URL**")
            url_result: UploadURLResult = get_upload_url(connection, token)
            _append_history_upload_url(url_result)
            if (
                not url_result.ok
                or not url_result.signed_url
                or not url_result.file_source
            ):
                summary = _format_error_summary(
                    "Could not allocate an upload URL",
                    url_result.error_message or "Unknown error.",
                    url_result.http_status,
                    url_result.correlation_id,
                )
                status_box.update(
                    label="Upload failed at Phase 1", state="error"
                )
                raise _PipelineFailureError(summary)
            file_source = url_result.file_source
            file_id = url_result.file_id or "(not supplied)"
            st.success("✅ Signed URL received.")

            # ---------- Phase 2: PUT bytes ------------------------------
            st.write(
                f"**2. Uploading file bytes** "
                f"({_humanize_bytes(size_bytes)})"
            )
            bytes_result: UploadBytesResult = upload_file_bytes(
                url_result.signed_url,
                file_bytes,
                content_type=content_type,
                timeout=120,
            )
            _append_history_upload_bytes(bytes_result)
            if not bytes_result.ok:
                summary = (
                    "❌ File bytes could not be uploaded to Azure Blob "
                    "Storage. "
                    f"Reason: {bytes_result.error_message or 'Unknown error.'}"
                )
                detail_bits: list[str] = []
                if bytes_result.http_status is not None:
                    detail_bits.append(f"HTTP {bytes_result.http_status}")
                detail_bits.append(f"file id: `{file_id}`")
                summary = (
                    summary + "  \n_" + " · ".join(detail_bits) + "_"
                )
                status_box.update(
                    label="Upload failed at Phase 2", state="error"
                )
                raise _PipelineFailureError(summary)
            st.success(
                f"✅ Uploaded {_humanize_bytes(bytes_result.bytes_uploaded)}."
            )

            # ---------- Phase 3: metadata POST --------------------------
            st.write("**3. Registering metadata**")
            metadata_result: FileMetadataResult = post_file_metadata(
                connection,
                token,
                file_source=file_source,
                file_id=url_result.file_id or "",
                display_name=resolved_display_name,
                description=resolved_description,
                legal_tag=legal_tag,
                acl_owners=acl_owners,
                acl_viewers=acl_viewers,
            )
            _append_history_metadata(metadata_result)
            if not metadata_result.ok:
                # Critical edge case: bytes landed, metadata didn't —
                # preserve the file id so the operator can recover.
                summary = (
                    "⚠️ File uploaded but metadata registration failed "
                    f"— file id: `{file_id}`. The bytes are in storage "
                    "but no record exists. Retry with this file id or "
                    "contact an admin to register metadata manually.  \n"
                    f"Reason: "
                    f"{metadata_result.error_message or 'Unknown error.'}"
                )
                detail_bits = []
                if metadata_result.http_status is not None:
                    detail_bits.append(
                        f"HTTP {metadata_result.http_status}"
                    )
                if metadata_result.correlation_id:
                    detail_bits.append(
                        f"correlation `{metadata_result.correlation_id}`"
                    )
                if detail_bits:
                    summary = (
                        summary + "  \n_" + " · ".join(detail_bits) + "_"
                    )
                status_box.update(
                    label="Upload failed at Phase 3", state="error"
                )
                raise _PipelineFailureError(summary)

            st.session_state[FILE_UPLOAD_LAST_RESULT_KEY] = metadata_result
            status_box.update(label="✅ File registered", state="complete")
    except _PipelineFailureError as exc:
        message = str(exc)
        st.session_state[FILE_UPLOAD_LAST_ERROR_KEY] = message
        st.error(message)
        return

    st.rerun()


# ---------------------------------------------------------------------------
# Result panel
# ---------------------------------------------------------------------------


def _render_result_panel() -> None:
    """Render the success card after a completed upload."""
    result = st.session_state.get(FILE_UPLOAD_LAST_RESULT_KEY)
    if not isinstance(result, FileMetadataResult) or not result.ok:
        return
    if not result.record_id:
        return

    st.divider()
    st.subheader("Result")
    version_part = (
        f" (version {result.record_version})"
        if result.record_version is not None
        else ""
    )
    st.success(f"✅ Uploaded as record `{result.record_id}`{version_part}")
    st.caption("Copy the record id below to reference it from a manifest:")
    st.code(result.record_id, language=None)

    cols = st.columns(2)
    with cols[0]:
        st.page_link(
            SEARCH_PAGE_PATH,
            label="🔍 View in Search",
        )
    with cols[1]:
        if st.button("📤 Upload another", key="file_upload_upload_another"):
            st.session_state[FILE_UPLOAD_LAST_RESULT_KEY] = None
            st.session_state[FILE_UPLOAD_DISPLAY_NAME_KEY] = ""
            st.session_state[FILE_UPLOAD_DESCRIPTION_KEY] = ""
            st.rerun()


# ---------------------------------------------------------------------------
# History
# ---------------------------------------------------------------------------


def _render_history() -> None:
    """Render the latency chart, history table, and clear button."""
    history: list[dict[str, Any]] = st.session_state.get(
        FILE_UPLOAD_HISTORY_KEY, []
    )
    st.divider()
    st.subheader(f"History ({len(history)})")

    if not history:
        st.caption("No file upload API calls yet this session.")
        return

    if st.button("🧹 Clear history", key="file_upload_clear_history"):
        st.session_state[FILE_UPLOAD_HISTORY_KEY] = []
        st.rerun()

    chart_df = _history_to_chart_frame(history)
    if not chart_df.empty:
        st.line_chart(chart_df, y_label="latency (ms)")

    st.dataframe(
        _history_to_table_rows(history),
        use_container_width=True,
        hide_index=True,
    )


def _history_to_chart_frame(history: list[dict[str, Any]]) -> pd.DataFrame:
    """Pivot history into a timestamp-indexed frame, ok-only rows."""
    if not history:
        return pd.DataFrame()
    frame = pd.DataFrame(history)
    frame = frame[frame["ok"] == True]  # noqa: E712 - explicit boolean
    if frame.empty:
        return pd.DataFrame()
    pivoted = frame.pivot_table(
        index="timestamp",
        columns="endpoint",
        values="latency_ms",
        aggfunc="last",
    )
    return pivoted.sort_index()


def _history_to_table_rows(
    history: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Project history into newest-first rows for st.dataframe."""
    recent = list(reversed(history))[:HISTORY_DISPLAY_LIMIT]
    rows: list[dict[str, Any]] = []
    for entry in recent:
        rows.append(
            {
                "timestamp": entry.get("timestamp", ""),
                "endpoint": entry.get("endpoint", ""),
                "ok": "✅" if entry.get("ok") else "❌",
                "http_status": (
                    entry.get("http_status")
                    if entry.get("http_status") is not None
                    else "—"
                ),
                "latency_ms": f"{float(entry.get('latency_ms', 0.0)):.1f}",
                "correlation_id": entry.get("correlation_id") or "—",
                "error_message": entry.get("error_message") or "",
            }
        )
    return rows


def _append_history(
    *,
    endpoint: str,
    ok: bool,
    http_status: int | None,
    latency_ms: float,
    correlation_id: str | None,
    error_message: str | None,
) -> None:
    """Append one history row.  Append-only within the session."""
    history = st.session_state.get(FILE_UPLOAD_HISTORY_KEY, [])
    history.append(
        {
            "timestamp": datetime.now(tz=UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "endpoint": endpoint,
            "ok": ok,
            "http_status": http_status,
            "latency_ms": round(float(latency_ms), 1),
            "correlation_id": correlation_id,
            "error_message": error_message,
        }
    )
    st.session_state[FILE_UPLOAD_HISTORY_KEY] = history


def _append_history_upload_url(result: UploadURLResult) -> None:
    _append_history(
        endpoint=LABEL_UPLOAD_URL,
        ok=result.ok,
        http_status=result.http_status,
        latency_ms=result.latency_ms,
        correlation_id=result.correlation_id,
        error_message=result.error_message,
    )


def _append_history_upload_bytes(result: UploadBytesResult) -> None:
    _append_history(
        endpoint=LABEL_UPLOAD_BYTES,
        ok=result.ok,
        http_status=result.http_status,
        latency_ms=result.latency_ms,
        correlation_id=None,  # No correlation id on the Azure PUT.
        error_message=result.error_message,
    )


def _append_history_metadata(result: FileMetadataResult) -> None:
    _append_history(
        endpoint=LABEL_METADATA,
        ok=result.ok,
        http_status=result.http_status,
        latency_ms=result.latency_ms,
        correlation_id=result.correlation_id,
        error_message=result.error_message,
    )


# ---------------------------------------------------------------------------
# Misc helpers
# ---------------------------------------------------------------------------


def _set_sticky_error(message: str) -> None:
    """Pin a sticky error and render it directly on the page."""
    st.session_state[FILE_UPLOAD_LAST_ERROR_KEY] = message
    st.error(message)


def _format_error_summary(
    headline: str,
    message: str,
    http_status: int | None,
    correlation_id: str | None,
) -> str:
    """Compose a sticky-error summary (headline + message + HTTP + corr)."""
    parts = [f"❌ {headline}: {message}"]
    detail_bits: list[str] = []
    if http_status is not None:
        detail_bits.append(f"HTTP {http_status}")
    if correlation_id:
        detail_bits.append(f"correlation `{correlation_id}`")
    if detail_bits:
        parts.append("_" + " · ".join(detail_bits) + "_")
    return "  \n".join(parts)


def _humanize_bytes(size_bytes: int) -> str:
    """Return a human-readable size string (B / KB / MB / GB)."""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    if size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    if size_bytes < 1024 * 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.1f} MB"
    return f"{size_bytes / (1024 * 1024 * 1024):.2f} GB"


def _guess_mime(filename: str) -> str | None:
    """Best-effort MIME guess based on the filename extension."""
    guessed, _ = mimetypes.guess_type(filename)
    return guessed


main()
