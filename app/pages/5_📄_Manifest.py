"""Manifest-ingestion page for ADME.

Drives the operator through validate → legal-tag check → submit →
poll-workflow-status → verify-via-search.  Mirrors the entitlements page's
pre-flight chain, latency chart, history dataframe, and Re-run / Clear-history
primitives.
"""

from __future__ import annotations

import json
import sys
import time
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
    LegalTagCheckResult,
    SearchResult,
    WorkflowRunResult,
    WorkflowStatus,
)
from app.services.auth import AuthenticationError, get_token  # noqa: E402
from app.services.entitlements import fetch_groups  # noqa: E402
from app.services.ingestion import (  # noqa: E402
    TNO_SAMPLE_DESCRIPTION,
    TNO_SAMPLE_MANIFEST,
    check_legal_tag,
    get_workflow_status,
    submit_manifest,
    substitute_manifest_placeholders,
    validate_manifest_json,
)
from app.services.legal_tags import list_legal_tags  # noqa: E402
from app.services.manifest_builder import (  # noqa: E402
    DEFAULT_DATASET_KIND,
    build_file_generic_manifest,
)
from app.services.verification import search_records_by_kind  # noqa: E402

SETTINGS_PAGE_PATH = "pages/1_⚙️_Instance_Configuration.py"

# --- Locked session-state keys (Charlie tests these) ---------------------
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

# --- Sticky error key (persists across reruns until cleared) --------------
INGESTION_LAST_ERROR_KEY = "ingestion_last_error"

# --- Internal helper keys (not part of the locked contract) ---------------
LAST_WORKFLOW_RESULT_KEY = "ingestion_last_workflow_result"
VERIFICATION_RESULTS_KEY = "ingestion_verification_results"
VERIFICATION_RETRIES_KEY = "ingestion_verification_retries"
LAST_LEGAL_TAG_RESULT_KEY = "ingestion_last_legal_tag_result"
LAST_SUBMIT_RESULT_KEY = "ingestion_last_submit_result"
LAST_CORRELATION_ID_KEY = "ingestion_last_correlation_id"
RESOLVED_MANIFEST_TEXT_KEY = "ingestion_resolved_manifest_text"

# --- Dropdown option-cache keys (autorun-once load of legal tags + groups) -
INGESTION_OPTIONS_AUTORUN_KEY = "ingestion_options_autorun_done"
INGESTION_LEGAL_TAG_OPTIONS_KEY = "ingestion_legal_tag_options"
INGESTION_ACL_OWNER_OPTIONS_KEY = "ingestion_acl_owner_options"
INGESTION_ACL_VIEWER_OPTIONS_KEY = "ingestion_acl_viewer_options"

# --- Manifest Builder session keys (per Satya's contract) ----------------
# Locked names — Charlie tests these. `manifest_builder_file_id` is new
# (Kevin's finding: file_id is NOT recoverable from file_source alone).
MANIFEST_BUILDER_PICK_MODE_KEY = "manifest_builder_pick_mode"
MANIFEST_BUILDER_RECENT_CHOICE_KEY = "manifest_builder_recent_choice"
MANIFEST_BUILDER_FILE_SOURCE_KEY = "manifest_builder_file_source"
MANIFEST_BUILDER_FILE_ID_KEY = "manifest_builder_file_id"
MANIFEST_BUILDER_DISPLAY_NAME_KEY = "manifest_builder_display_name"
MANIFEST_BUILDER_DESCRIPTION_KEY = "manifest_builder_description"
MANIFEST_BUILDER_KIND_KEY = "manifest_builder_kind"
MANIFEST_BUILDER_PENDING_TEXT_KEY = "manifest_builder_pending_text"
MANIFEST_BUILDER_LAST_GENERATED_KEY = "manifest_builder_last_generated"

# Source for "From recent uploads" — entries with `record_id`,
# `display_name`, and `file_source` keys are surfaced. Today the File
# page populates `file_upload_history` only with latency rows, so this
# typically yields an empty list (paste mode default). Follow-up: have
# the File page also append richer entries with these fields on success.
FILE_UPLOAD_HISTORY_KEY = "file_upload_history"

HISTORY_DISPLAY_LIMIT = 20

# Polling cadence (seconds elapsed -> sleep before next rerun).
POLL_TIMEOUT_SECONDS = 30 * 60  # 30 minutes
VERIFICATION_RETRY_LIMIT = 3
VERIFICATION_RETRY_SLEEP_SECONDS = 5

# Endpoint labels for the in-session history.  The latency chart uses these
# verbatim except `search.{kind}` which already encodes the kind suffix.
LABEL_LEGAL_TAG_CHECK = "legal-tag-check"
LABEL_SUBMIT = "submit"
LABEL_POLL = "poll"


class _PipelineFailureError(Exception):
    """Raised inside the submit pipeline to short-circuit with a sticky error.

    The exception message is the operator-facing summary that will be both
    pinned to ``INGESTION_LAST_ERROR_KEY`` and rendered as an ``st.error``
    outside the ``st.status`` block so it does not vanish when the status
    box auto-collapses on failure.
    """


def main() -> None:
    """Render the ingestion page."""
    st.set_page_config(
        page_title="Manifest · ADME Control Plane",
        page_icon="📄",
        layout="wide",
    )
    st.title("📄 Submit a manifest")
    st.markdown(
        "Submit an OSDU manifest to the Workflow Service and verify it landed "
        "by querying the Search Service for the records you just loaded."
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

    # Sentinel-prime: if the Builder generated a manifest on the previous
    # run, copy the pending text into the editor's bound key BEFORE the
    # text_area renders. Streamlit forbids writing to a widget's bound
    # session key after the widget renders in the same run.
    if MANIFEST_BUILDER_PENDING_TEXT_KEY in st.session_state:
        st.session_state[MANIFEST_TEXT_KEY] = st.session_state.pop(
            MANIFEST_BUILDER_PENDING_TEXT_KEY
        )

    _render_sticky_error()
    _render_input_form(connection)
    _render_manifest_builder(connection)
    _render_manifest_editor()
    _render_action_row()
    _render_run_status()
    _render_verification_section()
    _render_history()


# ---------------------------------------------------------------------------
# Session bootstrap
# ---------------------------------------------------------------------------


def _ensure_page_defaults() -> None:
    """Initialize page-scoped session keys."""
    st.session_state.setdefault(MANIFEST_TEXT_KEY, "")
    st.session_state.setdefault(LEGAL_TAG_KEY, "")
    st.session_state.setdefault(ACL_OWNERS_KEY, "")
    st.session_state.setdefault(ACL_VIEWERS_KEY, "")
    st.session_state.setdefault(RUN_ID_KEY, None)
    st.session_state.setdefault(SUBMIT_STARTED_AT_KEY, None)
    st.session_state.setdefault(KINDS_KEY, [])
    st.session_state.setdefault(WORKFLOW_STATUS_KEY, None)
    st.session_state.setdefault(LAST_POLL_AT_KEY, None)
    st.session_state.setdefault(POLLING_ACTIVE_KEY, False)
    st.session_state.setdefault(HISTORY_KEY, [])
    st.session_state.setdefault(VERIFICATION_DONE_KEY, False)

    st.session_state.setdefault(LAST_WORKFLOW_RESULT_KEY, None)
    st.session_state.setdefault(VERIFICATION_RESULTS_KEY, [])

    # Manifest Builder defaults. Pick mode resolves dynamically when the
    # builder renders so it can default to "recent" when uploads exist.
    st.session_state.setdefault(MANIFEST_BUILDER_PICK_MODE_KEY, "paste")
    st.session_state.setdefault(MANIFEST_BUILDER_RECENT_CHOICE_KEY, "")
    st.session_state.setdefault(MANIFEST_BUILDER_FILE_SOURCE_KEY, "")
    st.session_state.setdefault(MANIFEST_BUILDER_FILE_ID_KEY, "")
    st.session_state.setdefault(MANIFEST_BUILDER_DISPLAY_NAME_KEY, "")
    st.session_state.setdefault(MANIFEST_BUILDER_DESCRIPTION_KEY, "")
    st.session_state.setdefault(MANIFEST_BUILDER_KIND_KEY, DEFAULT_DATASET_KIND)
    st.session_state.setdefault(MANIFEST_BUILDER_LAST_GENERATED_KEY, None)
    st.session_state.setdefault(VERIFICATION_RETRIES_KEY, {})
    st.session_state.setdefault(LAST_LEGAL_TAG_RESULT_KEY, None)
    st.session_state.setdefault(LAST_SUBMIT_RESULT_KEY, None)
    st.session_state.setdefault(LAST_CORRELATION_ID_KEY, None)
    st.session_state.setdefault(INGESTION_LAST_ERROR_KEY, None)

    st.session_state.setdefault(INGESTION_OPTIONS_AUTORUN_KEY, False)
    st.session_state.setdefault(INGESTION_LEGAL_TAG_OPTIONS_KEY, None)
    st.session_state.setdefault(INGESTION_ACL_OWNER_OPTIONS_KEY, None)
    st.session_state.setdefault(INGESTION_ACL_VIEWER_OPTIONS_KEY, None)


# ---------------------------------------------------------------------------
# Pre-flight
# ---------------------------------------------------------------------------


def _preflight_ok(connection: ADMEConnection | None) -> bool:
    """Return True when we have everything required to ingest."""
    if connection is None or not connection.is_valid():
        st.info(
            "No ADME connection is configured for this session. "
            "Open Instance Configuration to add your endpoint, identity details, and "
            "data partition."
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
                "Instance Configuration page to enable manifest ingestion."
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
            "Open Instance Configuration to sign in again or update credentials."
        )
        st.page_link(
            SETTINGS_PAGE_PATH,
            label="Open Instance Configuration",
            icon="⚙️",
        )
        return None
    except Exception as exc:  # noqa: BLE001 - never expose raw auth library details
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
# Input form
# ---------------------------------------------------------------------------


def _load_input_options(
    connection: ADMEConnection, *, force: bool = False
) -> None:
    """Autorun-once load of legal tags + entitlement groups for dropdowns.

    Populates ``INGESTION_LEGAL_TAG_OPTIONS_KEY``,
    ``INGESTION_ACL_OWNER_OPTIONS_KEY``, and ``INGESTION_ACL_VIEWER_OPTIONS_KEY``
    in session state. Each is set to a sorted ``list[str]`` on success or
    ``None`` on transport / auth / parse failure so the input form can fall
    back to a manual text input. The autorun guard
    (``INGESTION_OPTIONS_AUTORUN_KEY``) ensures we only call ADME once per
    session unless the operator clicks Refresh (``force=True``).
    """
    if not force and st.session_state.get(
        INGESTION_OPTIONS_AUTORUN_KEY, False
    ):
        return

    token = _acquire_token(connection)
    if token is None:
        # Mark autorun done so we don't retry every rerun while the operator
        # is fixing their connection. They can still hit Refresh.
        st.session_state[INGESTION_OPTIONS_AUTORUN_KEY] = True
        return

    # Legal tags
    try:
        with st.spinner("Loading legal tags…"):
            legal_result = list_legal_tags(connection, token, valid=True)
        if legal_result.ok and legal_result.items:
            names = sorted(
                {tag.name for tag in legal_result.items if tag.name}
            )
            st.session_state[INGESTION_LEGAL_TAG_OPTIONS_KEY] = (
                names or None
            )
        else:
            st.session_state[INGESTION_LEGAL_TAG_OPTIONS_KEY] = None
    except Exception:  # noqa: BLE001 - never block the page on a load failure
        st.session_state[INGESTION_LEGAL_TAG_OPTIONS_KEY] = None

    # ACL owners + viewers (single groups call, partitioned by suffix).
    try:
        with st.spinner("Loading entitlement groups…"):
            groups_result = fetch_groups(connection, token)
        owners, viewers = _partition_acl_groups(groups_result)
        st.session_state[INGESTION_ACL_OWNER_OPTIONS_KEY] = owners or None
        st.session_state[INGESTION_ACL_VIEWER_OPTIONS_KEY] = viewers or None
    except Exception:  # noqa: BLE001 - never block the page on a load failure
        st.session_state[INGESTION_ACL_OWNER_OPTIONS_KEY] = None
        st.session_state[INGESTION_ACL_VIEWER_OPTIONS_KEY] = None

    st.session_state[INGESTION_OPTIONS_AUTORUN_KEY] = True


def _partition_acl_groups(groups_result: Any) -> tuple[list[str], list[str]]:
    """Split a fetch_groups result into sorted owner / viewer email lists.

    Returns ``([], [])`` on transport failure or unexpected payload shape.
    Filters to OSDU-convention ACL groups: emails whose local-part starts
    with ``data.`` and ends with ``.owners`` (owners) or ``.viewers``
    (viewers). Other groups (users.*, service.*, etc.) are excluded.
    """
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


def _render_input_form(connection: ADMEConnection) -> None:
    """Render the legal-tag / ACL inputs and the TNO-sample expander."""
    refresh_clicked = st.button(
        "🔄 Refresh legal tags & groups",
        key="ingestion_refresh_options",
        help="Re-fetch legal tags and entitlement groups from ADME.",
    )
    if refresh_clicked:
        _load_input_options(connection, force=True)
        st.rerun()
    else:
        _load_input_options(connection)

    legal_options = st.session_state.get(INGESTION_LEGAL_TAG_OPTIONS_KEY)
    owner_options = st.session_state.get(INGESTION_ACL_OWNER_OPTIONS_KEY)
    viewer_options = st.session_state.get(INGESTION_ACL_VIEWER_OPTIONS_KEY)

    cols = st.columns(3)
    with cols[0]:
        _render_option_field(
            label="Legal tag name",
            session_key=LEGAL_TAG_KEY,
            options=legal_options,
            placeholder="opendes-tno-data",
            help_text=(
                "Fully qualified legal tag name. The page checks the tag "
                "exists before submitting."
            ),
            empty_caption=(
                "⚠️ Couldn't load legal tags — enter manually"
            ),
        )
    with cols[1]:
        _render_option_field(
            label="ACL owners group",
            session_key=ACL_OWNERS_KEY,
            options=owner_options,
            placeholder="data.default.owners@opendes.dataservices.energy",
            help_text=(
                "Email of the entitlements group that should own these "
                "records."
            ),
            empty_caption=(
                "⚠️ Couldn't load groups — enter manually"
            ),
        )
    with cols[2]:
        _render_option_field(
            label="ACL viewers group",
            session_key=ACL_VIEWERS_KEY,
            options=viewer_options,
            placeholder="data.default.viewers@opendes.dataservices.energy",
            help_text=(
                "Email of the entitlements group allowed to read these "
                "records."
            ),
            empty_caption=(
                "⚠️ Couldn't load groups — enter manually"
            ),
        )

    if TNO_SAMPLE_MANIFEST:
        with st.expander("📋 Try a real TNO sample manifest"):
            if TNO_SAMPLE_DESCRIPTION:
                st.markdown(TNO_SAMPLE_DESCRIPTION)
            st.caption(
                "The sample contains `{{LEGAL_TAG}}`, `{{ACL_OWNERS}}`, "
                "`{{ACL_VIEWERS}}`, and `{{DATA_PARTITION_ID}}` "
                "placeholders.  They are substituted at submit time using "
                "the inputs above and the active connection's data "
                "partition."
            )
            if st.button(
                "Insert TNO sample into editor",
                key="ingestion_insert_sample",
            ):
                st.session_state[MANIFEST_TEXT_KEY] = TNO_SAMPLE_MANIFEST
                st.rerun()
    else:
        st.caption(
            "ℹ️ The TNO reference sample is not yet available in this build."
        )

    # Reference unused arg defensively so future linters don't complain about
    # the parameter; the connection is consumed by the rest of the page.
    _ = connection


def _render_option_field(
    *,
    label: str,
    session_key: str,
    options: list[str] | None,
    placeholder: str,
    help_text: str,
    empty_caption: str,
) -> None:
    """Render a selectbox when options loaded; otherwise a text_input fallback.

    ``options=None`` means the API call failed or returned nothing useful;
    the field falls back to ``st.text_input`` so the operator can type the
    value manually. ``options=[...]`` is rendered as ``st.selectbox`` with a
    leading blank entry so the field starts empty (the pre-pipeline gate
    enforces non-empty values before submit).
    """
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
        # Preserve any pre-existing value (e.g. a manual entry that was
        # later refreshed) so streamlit doesn't error on a stale selection.
        final_options.append(current)
    st.selectbox(
        label,
        options=final_options,
        key=session_key,
        help=help_text,
    )


# ---------------------------------------------------------------------------
# Manifest Builder (expander above the editor)
# ---------------------------------------------------------------------------


GENERATE_MANIFEST_LABEL = "Generate manifest"


def _recent_uploads() -> list[dict[str, Any]]:
    """Return file_upload_history entries that look like recent uploads.

    A "recent upload" entry has non-empty ``record_id``, ``display_name``,
    and ``file_source`` string fields. Other entries (e.g. latency rows
    today's File page emits) are filtered out so the selectbox only shows
    real picks.
    """
    history = st.session_state.get(FILE_UPLOAD_HISTORY_KEY, [])
    if not isinstance(history, list):
        return []
    out: list[dict[str, Any]] = []
    for entry in history:
        if not isinstance(entry, dict):
            continue
        record_id = entry.get("record_id")
        display_name = entry.get("display_name")
        file_source = entry.get("file_source")
        if (
            isinstance(record_id, str)
            and record_id
            and isinstance(display_name, str)
            and display_name
            and isinstance(file_source, str)
            and file_source
        ):
            out.append(
                {
                    "record_id": record_id,
                    "display_name": display_name,
                    "file_source": file_source,
                    "description": str(entry.get("description") or ""),
                }
            )
    # Newest first for the selectbox.
    return list(reversed(out))


def _render_manifest_builder(connection: ADMEConnection) -> None:
    """Render the Builder expander above the manifest text editor.

    The expander offers two pick modes (recent uploads / paste manually),
    a kind selectbox locked to ``DEFAULT_DATASET_KIND`` for v1, and a
    Generate button that calls
    :func:`app.services.manifest_builder.build_file_generic_manifest`
    using the legal-tag and ACL selectbox values from the form above.
    On success it primes the editor via ``MANIFEST_BUILDER_PENDING_TEXT_KEY``
    and reruns. Hand-edited manifests still work — the Builder is additive.
    """
    recent = _recent_uploads()

    # Default the radio to "recent" when uploads exist, "paste" otherwise.
    if recent and not st.session_state.get(MANIFEST_BUILDER_PICK_MODE_KEY):
        st.session_state[MANIFEST_BUILDER_PICK_MODE_KEY] = "recent"
    if not recent:
        st.session_state[MANIFEST_BUILDER_PICK_MODE_KEY] = "paste"

    with st.expander("🛠️ Build manifest", expanded=False):
        st.caption(
            "Build a workflow-ready `dataset--File.Generic:1.0.0` manifest "
            "from a recent upload (or by pasting a FileSource). The "
            "generated JSON is loaded into the editor below for review "
            "before you click **Validate & Ingest**."
        )

        mode_options = ["recent", "paste"]
        mode_index = (
            0
            if st.session_state.get(MANIFEST_BUILDER_PICK_MODE_KEY) == "recent"
            else 1
        )
        st.radio(
            "Pick the file source",
            options=mode_options,
            index=mode_index,
            format_func=lambda v: (
                "📂 From recent uploads" if v == "recent" else "✏️ Paste manually"
            ),
            key=MANIFEST_BUILDER_PICK_MODE_KEY,
            horizontal=True,
        )

        pick_mode = st.session_state.get(
            MANIFEST_BUILDER_PICK_MODE_KEY, "paste"
        )
        picked: dict[str, Any] | None = None

        if pick_mode == "recent":
            if not recent:
                st.info(
                    "No recent uploads in this session — use Paste mode."
                )
            else:
                labels = {
                    entry["record_id"]: (
                        f"{entry['display_name']} — {entry['record_id']}"
                    )
                    for entry in recent
                }
                options = [entry["record_id"] for entry in recent]
                # If the previously selected record id is no longer in
                # history (cleared mid-session), fall back to the first.
                current = st.session_state.get(
                    MANIFEST_BUILDER_RECENT_CHOICE_KEY, ""
                )
                if current not in options:
                    st.session_state[MANIFEST_BUILDER_RECENT_CHOICE_KEY] = (
                        options[0]
                    )
                st.selectbox(
                    "Recent upload",
                    options=options,
                    format_func=lambda rid: labels.get(rid, rid),
                    key=MANIFEST_BUILDER_RECENT_CHOICE_KEY,
                )
                picked_id = st.session_state[
                    MANIFEST_BUILDER_RECENT_CHOICE_KEY
                ]
                picked = next(
                    (e for e in recent if e["record_id"] == picked_id), None
                )
                # Pre-fill display name + description from the picked entry
                # if those fields are still blank (don't clobber operator
                # edits across reruns).
                if picked is not None:
                    if not st.session_state.get(
                        MANIFEST_BUILDER_DISPLAY_NAME_KEY
                    ):
                        st.session_state[
                            MANIFEST_BUILDER_DISPLAY_NAME_KEY
                        ] = picked["display_name"]
                    if not st.session_state.get(
                        MANIFEST_BUILDER_DESCRIPTION_KEY
                    ):
                        st.session_state[
                            MANIFEST_BUILDER_DESCRIPTION_KEY
                        ] = picked["description"]
        else:
            paste_cols = st.columns(2)
            with paste_cols[0]:
                st.text_input(
                    "FileSource (Azure blob path)",
                    key=MANIFEST_BUILDER_FILE_SOURCE_KEY,
                    placeholder=(
                        "https://<account>.blob.core.windows.net/<container>/<path>"
                    ),
                    help=(
                        "The opaque Azure blob path returned by "
                        "`GET /uploadURL` as `FileSource`."
                    ),
                )
            with paste_cols[1]:
                st.text_input(
                    "File record id",
                    key=MANIFEST_BUILDER_FILE_ID_KEY,
                    placeholder="opendes:dataset--File.Generic:abc123",
                    help=(
                        "The `FileID` returned alongside `FileSource` from "
                        "`GET /uploadURL`. Not recoverable from FileSource "
                        "alone — paste both."
                    ),
                )

        st.text_input(
            "Display name",
            key=MANIFEST_BUILDER_DISPLAY_NAME_KEY,
            placeholder="my-dataset.csv",
        )
        st.text_area(
            "Description (optional)",
            key=MANIFEST_BUILDER_DESCRIPTION_KEY,
            placeholder="Short description of what this dataset contains.",
            height=80,
        )
        st.selectbox(
            "Kind",
            options=[DEFAULT_DATASET_KIND],
            key=MANIFEST_BUILDER_KIND_KEY,
            help=(
                "Locked to `dataset--File.Generic:1.0.0` for v1. More "
                "kinds will be added as the workflow supports them."
            ),
        )

        clicked = st.button(
            GENERATE_MANIFEST_LABEL,
            type="primary",
            key="manifest_builder_generate_button",
        )

        if clicked:
            _handle_generate_click(
                connection=connection,
                pick_mode=pick_mode,
                picked=picked,
            )


def _handle_generate_click(
    *,
    connection: ADMEConnection,
    pick_mode: str,
    picked: dict[str, Any] | None,
) -> None:
    """Validate Builder inputs, call the service, prime the editor."""
    if pick_mode == "recent":
        if picked is None:
            st.error(
                "❌ No recent upload selected — pick one from the "
                "dropdown or switch to Paste mode."
            )
            return
        file_source = picked["file_source"]
        file_id = picked["record_id"]
    else:
        file_source = str(
            st.session_state.get(MANIFEST_BUILDER_FILE_SOURCE_KEY) or ""
        ).strip()
        file_id = str(
            st.session_state.get(MANIFEST_BUILDER_FILE_ID_KEY) or ""
        ).strip()

    display_name = str(
        st.session_state.get(MANIFEST_BUILDER_DISPLAY_NAME_KEY) or ""
    ).strip()
    description = str(
        st.session_state.get(MANIFEST_BUILDER_DESCRIPTION_KEY) or ""
    )
    kind = str(
        st.session_state.get(MANIFEST_BUILDER_KIND_KEY) or ""
    ).strip() or DEFAULT_DATASET_KIND
    legal_tag = str(st.session_state.get(LEGAL_TAG_KEY) or "").strip()
    acl_owners = str(st.session_state.get(ACL_OWNERS_KEY) or "").strip()
    acl_viewers = str(st.session_state.get(ACL_VIEWERS_KEY) or "").strip()

    missing: list[str] = []
    if not file_source:
        missing.append("FileSource")
    if not file_id:
        missing.append("File record id")
    if not display_name:
        missing.append("Display name")
    if not legal_tag:
        missing.append("Legal tag (set above)")
    if not acl_owners:
        missing.append("ACL owners group (set above)")
    if not acl_viewers:
        missing.append("ACL viewers group (set above)")
    if missing:
        bullets = "\n".join(f"- {field}" for field in missing)
        st.error(
            "❌ Cannot generate manifest — please fill in:\n" + bullets
        )
        return

    try:
        manifest = build_file_generic_manifest(
            file_source=file_source,
            file_id=file_id,
            display_name=display_name,
            description=description,
            kind=kind,
            legal_tag=legal_tag,
            acl_owners=acl_owners,
            acl_viewers=acl_viewers,
            data_partition_id=connection.data_partition_id,
        )
    except ValueError as exc:
        st.error(f"❌ Could not build manifest: {exc}")
        return

    st.session_state[MANIFEST_BUILDER_LAST_GENERATED_KEY] = manifest
    st.session_state[MANIFEST_BUILDER_PENDING_TEXT_KEY] = json.dumps(
        manifest, indent=2
    )
    st.success("✅ Manifest generated — loaded into the editor below.")
    st.rerun()


# ---------------------------------------------------------------------------
# Manifest editor + actions
# ---------------------------------------------------------------------------


def _render_manifest_editor() -> None:
    """Render the manifest text-area."""
    st.text_area(
        "Manifest JSON",
        key=MANIFEST_TEXT_KEY,
        height=400,
        placeholder=(
            "Paste the workflow JSON payload here.  The page expects an "
            "object with an `executionContext.manifest` block containing "
            "`ReferenceData`, `MasterData`, or `Data` lists."
        ),
    )


def _render_action_row() -> None:
    """Render the Validate & Ingest button (and clear-history shortcut)."""
    history_count = len(st.session_state.get(HISTORY_KEY, []))
    cols = st.columns([1, 1, 6])
    with cols[0]:
        validate_clicked = st.button(
            "Validate & Ingest",
            type="primary",
            key="ingestion_submit_button",
        )
    with cols[1]:
        if history_count:
            clear_clicked = st.button(
                "Clear history",
                key="ingestion_clear_history_top",
            )
        else:
            clear_clicked = False

    if clear_clicked:
        _clear_history_and_state()
        st.rerun()

    if validate_clicked:
        connection = get_connection(st.session_state)
        if connection is None:
            return  # pre-flight already short-circuited; defensive
        _run_submit_pipeline(connection)


# ---------------------------------------------------------------------------
# Submit pipeline (steps 1-3, then handing off to polling)
# ---------------------------------------------------------------------------


def _run_submit_pipeline(connection: ADMEConnection) -> None:
    """Execute the validate → legal-tag → submit flow on button click.

    Steps 4 (poll) and 5 (verify) run on subsequent reruns driven by the
    persisted run-id and workflow status.
    """
    # Every click clears the sticky error from any prior attempt.
    st.session_state[INGESTION_LAST_ERROR_KEY] = None

    raw_text = st.session_state.get(MANIFEST_TEXT_KEY, "")
    legal_tag = st.session_state.get(LEGAL_TAG_KEY, "").strip()
    acl_owners = st.session_state.get(ACL_OWNERS_KEY, "").strip()
    acl_viewers = st.session_state.get(ACL_VIEWERS_KEY, "").strip()

    # ---------- Pre-pipeline gate: required-field check ------------------
    # Render directly on the page (NOT inside st.status) so the message
    # never gets swallowed by an auto-collapsed status block.
    missing: list[str] = []
    if not legal_tag:
        missing.append("Legal tag name")
    if not acl_owners:
        missing.append("ACL owners group")
    if not acl_viewers:
        missing.append("ACL viewers group")
    if not raw_text.strip():
        missing.append("Manifest JSON")
    if missing:
        bullets = "\n".join(f"- {field}" for field in missing)
        msg = (
            "❌ Cannot ingest yet — please fill in:\n"
            f"{bullets}"
        )
        st.session_state[INGESTION_LAST_ERROR_KEY] = msg
        st.error(msg)
        return

    status_box = st.status("Submitting manifest…", expanded=True)

    try:
        with status_box:
            # ---------- Step 1: validate + substitute placeholders -----
            st.write("**1. Validate JSON & substitute placeholders**")
            ok, error_message, parsed = validate_manifest_json(raw_text)
            if not ok or parsed is None:
                st.error(f"❌ Manifest is not valid: {error_message}")
                status_box.update(label="Validation failed", state="error")
                raise _PipelineFailureError(
                    f"❌ Manifest is not valid: {error_message}"
                )

            substituted_text = raw_text
            if "{{" in raw_text:
                try:
                    substituted_text = substitute_manifest_placeholders(
                        raw_text,
                        data_partition_id=connection.data_partition_id,
                        legal_tag_name=legal_tag,
                        acl_owners=acl_owners,
                        acl_viewers=acl_viewers,
                    )
                except ValueError as exc:
                    st.error(f"❌ Could not substitute placeholders: {exc}")
                    status_box.update(
                        label="Substitution failed", state="error"
                    )
                    raise _PipelineFailureError(
                        f"❌ Could not substitute placeholders: {exc}"
                    ) from exc
                ok, error_message, parsed = validate_manifest_json(
                    substituted_text
                )
                if not ok or parsed is None:
                    st.error(
                        "❌ Manifest is not valid after placeholder "
                        f"substitution: {error_message}"
                    )
                    status_box.update(
                        label="Validation failed after substitution",
                        state="error",
                    )
                    raise _PipelineFailureError(
                        "❌ Manifest is not valid after placeholder "
                        f"substitution: {error_message}"
                    )

            st.session_state[RESOLVED_MANIFEST_TEXT_KEY] = substituted_text
            st.success("✅ Manifest JSON validated.")

            # ---------- Step 2: legal-tag check ------------------------
            st.write("**2. Check legal tag exists**")
            token = _acquire_token(connection)
            if token is None:
                status_box.update(
                    label="Token acquisition failed", state="error"
                )
                raise _PipelineFailureError(
                    "❌ Could not acquire an ADME token. "
                    "Open Instance Configuration to sign in again "
                    "or update credentials."
                )

            legal_result = check_legal_tag(connection, token, legal_tag)
            _append_history_legal(legal_result)
            st.session_state[LAST_LEGAL_TAG_RESULT_KEY] = legal_result
            if not legal_result.ok:
                _render_legal_tag_error(legal_result)
                status_box.update(label="Legal tag missing", state="error")
                raise _PipelineFailureError(
                    _format_error_summary(
                        "Legal tag check failed",
                        legal_result.error_message or "Unknown error.",
                        legal_result.http_status,
                        legal_result.correlation_id,
                    )
                )
            st.success(
                f"✅ Legal tag `{legal_tag}` exists in this partition."
            )

            # ---------- Step 3: submit manifest ------------------------
            st.write("**3. Submit manifest to Workflow service**")
            submit_result = submit_manifest(connection, token, parsed)
            _append_history_workflow(submit_result, label=LABEL_SUBMIT)
            st.session_state[LAST_SUBMIT_RESULT_KEY] = submit_result
            st.session_state[LAST_WORKFLOW_RESULT_KEY] = submit_result
            if submit_result.correlation_id:
                st.session_state[LAST_CORRELATION_ID_KEY] = (
                    submit_result.correlation_id
                )

            if not submit_result.ok or not submit_result.run_id:
                _render_workflow_error(
                    submit_result, headline="Submit failed"
                )
                status_box.update(label="Submit failed", state="error")
                raise _PipelineFailureError(
                    _format_error_summary(
                        "Submit failed",
                        submit_result.error_message
                        or submit_result.message
                        or "Unknown error.",
                        submit_result.http_status,
                        submit_result.correlation_id,
                    )
                )

            # Persist polling state and the unique kinds we'll verify later.
            st.session_state[RUN_ID_KEY] = submit_result.run_id
            st.session_state[SUBMIT_STARTED_AT_KEY] = datetime.now(tz=UTC)
            st.session_state[KINDS_KEY] = _extract_unique_kinds(parsed)
            st.session_state[WORKFLOW_STATUS_KEY] = submit_result.status
            st.session_state[POLLING_ACTIVE_KEY] = True
            st.session_state[VERIFICATION_DONE_KEY] = False
            st.session_state[VERIFICATION_RESULTS_KEY] = []
            st.session_state[VERIFICATION_RETRIES_KEY] = {}

            st.success(
                f"✅ Workflow accepted — run id `{submit_result.run_id}`. "
                "Polling status…"
            )
            status_box.update(
                label="Submitted, polling status", state="running"
            )
    except _PipelineFailureError as exc:
        # The status block has already been marked state="error" so it stays
        # expanded.  Pin the summary to session state and also render an
        # st.error outside the (now-failed) status block.
        message = str(exc)
        st.session_state[INGESTION_LAST_ERROR_KEY] = message
        st.error(message)
        return

    # Trigger a rerun so the polling block (rendered below) takes over.
    st.rerun()


# ---------------------------------------------------------------------------
# Polling & status display (Step 4)
# ---------------------------------------------------------------------------


def _render_run_status() -> None:
    """Render the workflow-status block and (when active) drive polling."""
    run_id = st.session_state.get(RUN_ID_KEY)
    started_at = st.session_state.get(SUBMIT_STARTED_AT_KEY)
    if not run_id or not isinstance(started_at, datetime):
        return

    st.divider()
    st.subheader("Workflow run")

    status: WorkflowStatus | None = st.session_state.get(WORKFLOW_STATUS_KEY)
    elapsed = (datetime.now(tz=UTC) - started_at).total_seconds()

    cols = st.columns([2, 1, 1])
    with cols[0]:
        st.markdown(f"**Run id:** `{run_id}`")
        last_correlation = st.session_state.get(LAST_CORRELATION_ID_KEY)
        if last_correlation:
            st.caption(f"Last correlation id: `{last_correlation}`")
    with cols[1]:
        st.metric("Elapsed", _format_elapsed(elapsed))
        st.metric("Status", _status_label(status))
    with cols[2]:
        manual_refresh = st.button(
            "🔄 Refresh status now",
            key="ingestion_manual_refresh",
            disabled=not st.session_state.get(POLLING_ACTIVE_KEY, False),
        )

    last_result: WorkflowRunResult | None = st.session_state.get(
        LAST_WORKFLOW_RESULT_KEY
    )
    if last_result is not None and last_result.raw_status:
        st.caption(f"Server-supplied status: `{last_result.raw_status}`")

    progress_value = min(elapsed / POLL_TIMEOUT_SECONDS, 1.0)
    st.progress(
        progress_value,
        text="Visual elapsed-time indicator (not a real progress estimate)",
    )

    polling_active = bool(st.session_state.get(POLLING_ACTIVE_KEY, False))
    if not polling_active:
        # Terminal state — render appropriate banner.
        if status == WorkflowStatus.FAILED and last_result is not None:
            _render_workflow_error(
                last_result,
                headline="Workflow failed",
            )
        return

    # Timeout guard.
    if elapsed >= POLL_TIMEOUT_SECONDS:
        synthetic = WorkflowRunResult(
            workflow_id=last_result.workflow_id if last_result else None,
            run_id=run_id,
            status=WorkflowStatus.FAILED,
            raw_status="timed_out",
            message="Polling timed out after 30 minutes.",
            ok=False,
            http_status=None,
            latency_ms=0.0,
            correlation_id=None,
            error_message="Polling timed out after 30 minutes.",
            raw_response=None,
        )
        _append_history_workflow(synthetic, label=LABEL_POLL)
        st.session_state[LAST_WORKFLOW_RESULT_KEY] = synthetic
        st.session_state[WORKFLOW_STATUS_KEY] = WorkflowStatus.FAILED
        st.session_state[POLLING_ACTIVE_KEY] = False
        _render_workflow_error(synthetic, headline="Workflow timed out")
        st.session_state[INGESTION_LAST_ERROR_KEY] = _format_error_summary(
            "Workflow timed out",
            synthetic.error_message or "Polling timed out.",
            synthetic.http_status,
            synthetic.correlation_id,
        )
        return

    connection = get_connection(st.session_state)
    if connection is None:
        st.session_state[POLLING_ACTIVE_KEY] = False
        return
    token = _acquire_token(connection)
    if token is None:
        st.session_state[POLLING_ACTIVE_KEY] = False
        return

    poll_result = get_workflow_status(connection, token, run_id)
    _append_history_workflow(poll_result, label=LABEL_POLL)
    st.session_state[LAST_WORKFLOW_RESULT_KEY] = poll_result
    st.session_state[WORKFLOW_STATUS_KEY] = poll_result.status
    st.session_state[LAST_POLL_AT_KEY] = datetime.now(tz=UTC)
    if poll_result.correlation_id:
        st.session_state[LAST_CORRELATION_ID_KEY] = poll_result.correlation_id

    if poll_result.status == WorkflowStatus.FINISHED:
        st.session_state[POLLING_ACTIVE_KEY] = False
        st.session_state[VERIFICATION_DONE_KEY] = False
        st.success("✅ Workflow finished — verifying records…")
        st.rerun()
        return

    if poll_result.status == WorkflowStatus.FAILED:
        st.session_state[POLLING_ACTIVE_KEY] = False
        _render_workflow_error(poll_result, headline="Workflow failed")
        st.session_state[INGESTION_LAST_ERROR_KEY] = _format_error_summary(
            "Workflow failed",
            poll_result.error_message
            or poll_result.message
            or "Unknown error.",
            poll_result.http_status,
            poll_result.correlation_id,
        )
        return

    # Still IN_PROGRESS / UNKNOWN — schedule the next poll.
    if manual_refresh:
        st.rerun()
        return

    sleep_seconds = _poll_sleep_seconds(elapsed)
    time.sleep(sleep_seconds)
    st.rerun()


def _poll_sleep_seconds(elapsed: float) -> int:
    """Return the next-poll sleep using the locked cadence ladder."""
    if elapsed < 30:
        return 2
    if elapsed < 5 * 60:
        return 5
    return 10


def _format_elapsed(elapsed: float) -> str:
    """Return ``mm:ss`` formatted elapsed time."""
    seconds = max(int(elapsed), 0)
    return f"{seconds // 60:02d}:{seconds % 60:02d}"


def _status_label(status: WorkflowStatus | None) -> str:
    """Return the friendly display string for a workflow status."""
    if status is None:
        return "—"
    mapping = {
        WorkflowStatus.IN_PROGRESS: "🟡 In progress",
        WorkflowStatus.FINISHED: "✅ Finished",
        WorkflowStatus.FAILED: "❌ Failed",
        WorkflowStatus.UNKNOWN: "⚪ Unknown",
    }
    return mapping.get(status, str(status))


# ---------------------------------------------------------------------------
# Verification (Step 5)
# ---------------------------------------------------------------------------


def _render_verification_section() -> None:
    """Auto-run verification once status=FINISHED, then render the result."""
    status: WorkflowStatus | None = st.session_state.get(WORKFLOW_STATUS_KEY)
    if status != WorkflowStatus.FINISHED:
        return

    if not st.session_state.get(VERIFICATION_DONE_KEY, False):
        connection = get_connection(st.session_state)
        if connection is None:
            return
        token = _acquire_token(connection)
        if token is None:
            return
        _run_verification(connection, token)
        st.session_state[VERIFICATION_DONE_KEY] = True

    _render_verification_results()


def _run_verification(connection: ADMEConnection, token: str) -> None:
    """Search every unique kind, retrying zero-counts up to 3× with sleep."""
    kinds: list[str] = list(st.session_state.get(KINDS_KEY, []))
    retries: dict[str, int] = dict(
        st.session_state.get(VERIFICATION_RETRIES_KEY, {})
    )
    final_results: dict[str, SearchResult] = {}

    for kind in kinds:
        attempts = 0
        result = search_records_by_kind(connection, token, kind)
        _append_history_search(result)
        attempts += 1
        while (
            result.ok
            and result.count == 0
            and attempts < VERIFICATION_RETRY_LIMIT
        ):
            time.sleep(VERIFICATION_RETRY_SLEEP_SECONDS)
            result = search_records_by_kind(connection, token, kind)
            _append_history_search(result)
            attempts += 1
        retries[kind] = attempts
        final_results[kind] = result

    st.session_state[VERIFICATION_RESULTS_KEY] = list(final_results.values())
    st.session_state[VERIFICATION_RETRIES_KEY] = retries


def _render_verification_results() -> None:
    """Render the verification dataframe and the summary banner."""
    results: list[SearchResult] = list(
        st.session_state.get(VERIFICATION_RESULTS_KEY, [])
    )
    if not results:
        return

    st.subheader("Verification")
    rows: list[dict[str, Any]] = []
    for result in results:
        rows.append(
            {
                "kind": result.kind,
                "count": result.count,
                "ok": "✅" if result.ok else "❌",
                "http_status": (
                    result.http_status
                    if result.http_status is not None
                    else "—"
                ),
                "latency_ms": f"{float(result.latency_ms):.1f}",
                "correlation_id": result.correlation_id or "—",
            }
        )
    st.dataframe(rows, use_container_width=True, hide_index=True)

    total_records = sum(r.count for r in results if r.ok)
    all_have_records = all(r.ok and r.count > 0 for r in results)
    any_zero_after_retries = any(r.ok and r.count == 0 for r in results)
    any_failed = any(not r.ok for r in results)

    if all_have_records:
        st.success(
            f"✅ Ingestion verified — {total_records} records found across "
            f"{len(results)} kinds."
        )
    elif any_failed:
        st.error(
            "❌ Verification could not complete for one or more kinds. "
            "See the rows above for status and correlation ids."
        )
    elif any_zero_after_retries:
        st.warning(
            "⚠️ Ingestion completed but the search index has not caught up "
            "yet. Try refreshing search later."
        )


# ---------------------------------------------------------------------------
# History panel
# ---------------------------------------------------------------------------


def _render_history() -> None:
    """Render the latency chart, the history table, and the clear button."""
    history: list[dict[str, Any]] = st.session_state.get(HISTORY_KEY, [])
    st.divider()
    st.subheader(f"History ({len(history)})")

    if not history:
        st.caption("No ingestion API calls yet this session.")
        return

    if st.button("🧹 Clear history", key="ingestion_clear_history_bottom"):
        _clear_history_and_state()
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
    history = st.session_state.get(HISTORY_KEY, [])
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
    st.session_state[HISTORY_KEY] = history


def _append_history_legal(result: LegalTagCheckResult) -> None:
    _append_history(
        endpoint=LABEL_LEGAL_TAG_CHECK,
        ok=result.ok,
        http_status=result.http_status,
        latency_ms=result.latency_ms,
        correlation_id=result.correlation_id,
        error_message=result.error_message,
    )


def _append_history_workflow(
    result: WorkflowRunResult,
    *,
    label: str,
) -> None:
    _append_history(
        endpoint=label,
        ok=result.ok,
        http_status=result.http_status,
        latency_ms=result.latency_ms,
        correlation_id=result.correlation_id,
        error_message=result.error_message,
    )


def _append_history_search(result: SearchResult) -> None:
    _append_history(
        endpoint=f"search.{result.kind}",
        ok=result.ok,
        http_status=result.http_status,
        latency_ms=result.latency_ms,
        correlation_id=result.correlation_id,
        error_message=result.error_message,
    )


# ---------------------------------------------------------------------------
# Error rendering helpers
# ---------------------------------------------------------------------------


def _format_error_summary(
    headline: str,
    message: str,
    http_status: int | None,
    correlation_id: str | None,
) -> str:
    """Compose a sticky-error summary (headline + message + HTTP + corr-id)."""
    parts = [f"❌ {headline}: {message}"]
    detail_bits: list[str] = []
    if http_status is not None:
        detail_bits.append(f"HTTP {http_status}")
    if correlation_id:
        detail_bits.append(f"correlation `{correlation_id}`")
    if detail_bits:
        parts.append("_" + " · ".join(detail_bits) + "_")
    return "  \n".join(parts)


def _render_sticky_error() -> None:
    """Render the persistent error banner (if any) above the form.

    The banner survives reruns so transient ``st.status`` failures don't
    flash and disappear.  Cleared either by another "Validate & Ingest"
    click or by the operator pressing the "Dismiss error" button.
    """
    message = st.session_state.get(INGESTION_LAST_ERROR_KEY)
    if not message:
        return
    cols = st.columns([8, 1])
    with cols[0]:
        st.error(message)
    with cols[1]:
        if st.button("Dismiss error", key="ingestion_dismiss_error"):
            st.session_state[INGESTION_LAST_ERROR_KEY] = None
            st.rerun()


def _render_legal_tag_error(result: LegalTagCheckResult) -> None:
    """Render the operator-friendly legal-tag failure block."""
    message = result.error_message or "Unknown error."
    status_part = (
        f"HTTP {result.http_status}"
        if result.http_status is not None
        else "no HTTP response"
    )
    correlation_part = (
        f"correlation ID `{result.correlation_id}`"
        if result.correlation_id
        else "no correlation ID"
    )
    st.error(
        f"❌ Legal tag check failed: {message}  \n"
        f"_{status_part} · {correlation_part}_  \n"
        "Hint: create the legal tag in your ADME instance first, then "
        "click Validate & Ingest again."
    )


def _render_workflow_error(
    result: WorkflowRunResult,
    *,
    headline: str,
) -> None:
    """Render the standard workflow failure block + raw response."""
    message = result.error_message or result.message or "Unknown error."
    status_part = (
        f"HTTP {result.http_status}"
        if result.http_status is not None
        else "no HTTP response"
    )
    correlation_part = (
        f"correlation ID `{result.correlation_id}`"
        if result.correlation_id
        else "no correlation ID"
    )
    st.error(
        f"❌ {headline}: {message}  \n"
        f"_{status_part} · {correlation_part}_"
    )
    with st.expander("Raw response"):
        if result.raw_response is None:
            st.caption("No response body was returned.")
        elif isinstance(result.raw_response, str):
            st.code(result.raw_response, language="text")
        else:
            st.json(result.raw_response)


# ---------------------------------------------------------------------------
# Manifest helpers
# ---------------------------------------------------------------------------


def _extract_unique_kinds(parsed_manifest: dict) -> list[str]:
    """Return the deduplicated list of entity ``kind`` strings.

    Reads ``executionContext.manifest.{ReferenceData,MasterData,Data}`` lists
    and collects each item's ``kind``.  Skips the manifest envelope's own
    top-level ``kind`` (e.g. ``osdu:wks:Manifest:1.0.0``) — that is the
    schema of the envelope, not of the entities being ingested.  Order-
    preserving so the verification dataframe shows kinds in submission
    order.
    """
    seen: set[str] = set()
    ordered: list[str] = []
    execution_context = parsed_manifest.get("executionContext", {})
    if not isinstance(execution_context, dict):
        return ordered
    manifest = execution_context.get("manifest", {})
    if not isinstance(manifest, dict):
        return ordered
    for section in ("ReferenceData", "MasterData", "Data"):
        items = manifest.get(section, [])
        if not isinstance(items, list):
            continue
        for item in items:
            if not isinstance(item, dict):
                continue
            kind = item.get("kind")
            if isinstance(kind, str) and kind and kind not in seen:
                seen.add(kind)
                ordered.append(kind)
    return ordered


def _clear_history_and_state() -> None:
    """Reset the in-session history and all derived state.

    Preserves the manifest text and the form inputs so the operator can
    re-submit without re-pasting.  Run id is cleared because the run is
    over and a new submission will produce a new run id anyway.
    """
    st.session_state[HISTORY_KEY] = []
    st.session_state[RUN_ID_KEY] = None
    st.session_state[SUBMIT_STARTED_AT_KEY] = None
    st.session_state[KINDS_KEY] = []
    st.session_state[WORKFLOW_STATUS_KEY] = None
    st.session_state[LAST_POLL_AT_KEY] = None
    st.session_state[POLLING_ACTIVE_KEY] = False
    st.session_state[VERIFICATION_DONE_KEY] = False
    st.session_state[LAST_WORKFLOW_RESULT_KEY] = None
    st.session_state[VERIFICATION_RESULTS_KEY] = []
    st.session_state[VERIFICATION_RETRIES_KEY] = {}
    st.session_state[LAST_LEGAL_TAG_RESULT_KEY] = None
    st.session_state[LAST_SUBMIT_RESULT_KEY] = None
    st.session_state[LAST_CORRELATION_ID_KEY] = None


if __name__ == "__main__":
    main()
