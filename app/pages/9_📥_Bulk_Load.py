"""Bulk Load page — submit a registered OSDU dataset tier to ADME.

Wires Kevin's :mod:`app.services.bulk_loader` registry + preview + submit
generator into a Streamlit page. v1 ships reference-data only: master-data
and work-products tiers ship disabled in every dataset descriptor and are
surfaced read-only here.

The page enforces a mandatory **Preview gate**: the Submit button stays
disabled until the operator has clicked Preview for the current dataset/tier
combination. Changing dataset or tier invalidates the gate so the operator
can never submit a payload they didn't first inspect.
"""

from __future__ import annotations

import sys
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
    DatasetDescriptor,
    ManifestPreview,
    SubmitResult,
)
from app.services.auth import AuthenticationError, get_token  # noqa: E402
from app.services.bulk_loader import (  # noqa: E402
    DATA_ROOT,
    _clear_cache,
    list_datasets,
    preview_tier,
    submit_tier,
)
from app.services.entitlements import fetch_groups  # noqa: E402
from app.services.legal_tags import list_legal_tags  # noqa: E402

SETTINGS_PAGE_PATH = "pages/1_⚙️_Instance_Configuration.py"

# --- Locked session-state keys (tests assert these names) ----------------
BULK_DATASET_KEY = "bulk_dataset_id"
BULK_TIER_KEY = "bulk_tier"
BULK_LEGAL_TAG_KEY = "bulk_legal_tag"
BULK_ACL_OWNERS_KEY = "bulk_acl_owners"
BULK_ACL_VIEWERS_KEY = "bulk_acl_viewers"
BULK_PREVIEW_SEEN_KEY = "bulk_preview_seen"  # tuple[str, str] | None
BULK_PREVIEW_RESULTS_KEY = "bulk_preview_results"  # list[ManifestPreview]
BULK_SUBMIT_RESULTS_KEY = "bulk_submit_results"  # list[SubmitResult]
BULK_LAST_ERROR_KEY = "bulk_last_error"  # str | None

# --- Internal helper keys (not part of the locked contract) --------------
BULK_OPTIONS_AUTORUN_KEY = "bulk_options_autorun_done"
BULK_LEGAL_TAG_OPTIONS_KEY = "bulk_legal_tag_options"
BULK_ACL_OWNER_OPTIONS_KEY = "bulk_acl_owner_options"
BULK_ACL_VIEWER_OPTIONS_KEY = "bulk_acl_viewer_options"

PREVIEW_BUTTON_LABEL = "🔍 Preview manifests"
SUBMIT_BUTTON_LABEL = "🚀 Submit all manifests"
DISMISS_BUTTON_LABEL = "Dismiss error"
REFRESH_OPTIONS_LABEL = "🔄 Refresh legal tags & groups"


def main() -> None:
    """Render the Bulk Load page."""
    st.set_page_config(
        page_title="Bulk Load · ADME Control Plane",
        page_icon="📥",
        layout="wide",
    )
    st.title("📥 Bulk Load")
    st.markdown(
        "Submit a registered OSDU dataset (reference-data, master-data, or "
        "work-products) to your ADME instance. **v1 supports reference-data "
        "only.**"
    )

    ensure_session_defaults(st.session_state)
    _ensure_page_defaults()

    # Drop the registry cache on mount so freshly dropped dataset folders
    # appear without an app restart (per Satya §1).
    _clear_cache()

    connection = get_connection(st.session_state)
    if not _preflight_ok(connection):
        return
    assert connection is not None  # mypy — _preflight_ok guarantees this

    st.caption(
        f"Data partition: `{connection.data_partition_id}` · "
        f"Endpoint: `{connection.endpoint}`"
    )

    _render_sticky_error()

    datasets = list_datasets()
    if not datasets:
        st.warning(
            "No datasets are registered on disk. Add a folder under "
            "`app/data/datasets/<id>/` with a `dataset.json` descriptor."
        )
        return

    descriptor = _render_dataset_selector(datasets)
    _render_source_and_license(descriptor)
    tier_name = _render_tier_selector(descriptor)

    _render_input_form(connection)

    if tier_name is None:
        st.info(
            "No tiers are enabled for this dataset yet. Pick a different "
            "dataset or wait for the next vendor drop."
        )
        return

    # If the dataset or tier changed since the last preview, invalidate
    # the gate so the operator must Preview again before Submit.
    seen = st.session_state.get(BULK_PREVIEW_SEEN_KEY)
    current_key = (descriptor.id, tier_name)
    if seen is not None and seen != current_key:
        st.session_state[BULK_PREVIEW_SEEN_KEY] = None
        st.session_state[BULK_PREVIEW_RESULTS_KEY] = []

    _render_preview_section(descriptor, tier_name)
    _render_submit_section(connection, descriptor, tier_name)
    _render_results_section()


# ---------------------------------------------------------------------------
# Session bootstrap
# ---------------------------------------------------------------------------


def _ensure_page_defaults() -> None:
    """Initialize page-scoped session keys."""
    st.session_state.setdefault(BULK_DATASET_KEY, "")
    st.session_state.setdefault(BULK_TIER_KEY, "")
    st.session_state.setdefault(BULK_LEGAL_TAG_KEY, "")
    st.session_state.setdefault(BULK_ACL_OWNERS_KEY, "")
    st.session_state.setdefault(BULK_ACL_VIEWERS_KEY, "")
    st.session_state.setdefault(BULK_PREVIEW_SEEN_KEY, None)
    st.session_state.setdefault(BULK_PREVIEW_RESULTS_KEY, [])
    st.session_state.setdefault(BULK_SUBMIT_RESULTS_KEY, [])
    st.session_state.setdefault(BULK_LAST_ERROR_KEY, None)

    st.session_state.setdefault(BULK_OPTIONS_AUTORUN_KEY, False)
    st.session_state.setdefault(BULK_LEGAL_TAG_OPTIONS_KEY, None)
    st.session_state.setdefault(BULK_ACL_OWNER_OPTIONS_KEY, None)
    st.session_state.setdefault(BULK_ACL_VIEWER_OPTIONS_KEY, None)


# ---------------------------------------------------------------------------
# Pre-flight (mirrors Manifest page exactly)
# ---------------------------------------------------------------------------


def _preflight_ok(connection: ADMEConnection | None) -> bool:
    """Return True when we have everything required to run Bulk Load."""
    if connection is None or not connection.is_valid():
        st.info(
            "No ADME connection is configured for this session. "
            "Open Instance Configuration to add your endpoint, identity details, "
            "and data partition."
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
                "Instance Configuration page to enable Bulk Load."
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
# Sticky errors (same idiom as Manifest / Legal Tags pages)
# ---------------------------------------------------------------------------


def _set_sticky_error(message: str) -> None:
    st.session_state[BULK_LAST_ERROR_KEY] = message


def _clear_sticky_error() -> None:
    st.session_state[BULK_LAST_ERROR_KEY] = None


def _render_sticky_error() -> None:
    message = st.session_state.get(BULK_LAST_ERROR_KEY)
    if not message:
        return
    st.error(message)
    if st.button(DISMISS_BUTTON_LABEL, key="bulk_dismiss_error"):
        _clear_sticky_error()
        st.rerun()


# ---------------------------------------------------------------------------
# Dataset selector + source/license expander
# ---------------------------------------------------------------------------


def _render_dataset_selector(
    datasets: list[DatasetDescriptor],
) -> DatasetDescriptor:
    """Render the dataset dropdown and return the selected descriptor."""
    options = [d.id for d in datasets]
    labels = {d.id: d.display_name for d in datasets}

    # Default to the first dataset if nothing is selected yet, or if the
    # previously selected id is gone from the registry.
    current = str(st.session_state.get(BULK_DATASET_KEY) or "")
    if current not in options:
        st.session_state[BULK_DATASET_KEY] = options[0]

    selected_id = st.selectbox(
        "Dataset",
        options=options,
        format_func=lambda i: labels.get(i, i),
        key=BULK_DATASET_KEY,
        help="Datasets discovered under `app/data/datasets/<id>/dataset.json`.",
    )
    return next(d for d in datasets if d.id == selected_id)


def _render_source_and_license(descriptor: DatasetDescriptor) -> None:
    """Render the source URL + NOTICE.md expander for this dataset."""
    with st.expander("📄 Source & license", expanded=False):
        st.markdown(f"**Source:** [{descriptor.source_url}]({descriptor.source_url})")
        notice_text = _read_notice(descriptor)
        if notice_text is None:
            st.caption("NOTICE not available")
        else:
            st.markdown(notice_text)


def _read_notice(descriptor: DatasetDescriptor) -> str | None:
    """Return the NOTICE.md body for this dataset, or ``None`` if missing.

    The notice path is resolved under ``DATA_ROOT`` defensively — even for
    in-tree datasets we never read a file outside ``app/data/``.
    """
    try:
        candidate = (descriptor.root_dir / descriptor.notice_path).resolve()
        candidate.relative_to(DATA_ROOT)
        return candidate.read_text(encoding="utf-8")
    except (OSError, ValueError):
        return None


# ---------------------------------------------------------------------------
# Tier selector
# ---------------------------------------------------------------------------


def _render_tier_selector(descriptor: DatasetDescriptor) -> str | None:
    """Render the tier radio. Returns the selected tier name or ``None``.

    Only enabled tiers appear in the radio. Disabled tiers are listed in an
    ``st.info`` block underneath so the operator sees what's coming next
    without being able to submit against them.
    """
    enabled_tiers = [
        name for name, tier in descriptor.tiers.items() if tier.enabled
    ]
    disabled_tiers = [
        (name, tier.reason or "tier disabled")
        for name, tier in descriptor.tiers.items()
        if not tier.enabled
    ]

    selected: str | None = None
    if enabled_tiers:
        current = str(st.session_state.get(BULK_TIER_KEY) or "")
        if current not in enabled_tiers:
            st.session_state[BULK_TIER_KEY] = enabled_tiers[0]
        selected = st.radio(
            "Tier",
            options=enabled_tiers,
            key=BULK_TIER_KEY,
            horizontal=True,
            help="v1 supports reference-data only.",
        )

    if disabled_tiers:
        bullets = "\n".join(
            f"- **{name}** — {reason}" for name, reason in disabled_tiers
        )
        st.info("Disabled tiers (future):\n\n" + bullets)

    return selected


# ---------------------------------------------------------------------------
# Legal tag + ACL inputs (selectbox-with-fallback, mirrors Manifest page)
# ---------------------------------------------------------------------------


def _render_input_form(connection: ADMEConnection) -> None:
    """Render the legal-tag / ACL inputs."""
    refresh_clicked = st.button(
        REFRESH_OPTIONS_LABEL,
        key="bulk_refresh_options",
        help="Re-fetch legal tags and entitlement groups from ADME.",
    )
    if refresh_clicked:
        _load_input_options(connection, force=True)
        st.rerun()
    else:
        _load_input_options(connection)

    legal_options = st.session_state.get(BULK_LEGAL_TAG_OPTIONS_KEY)
    owner_options = st.session_state.get(BULK_ACL_OWNER_OPTIONS_KEY)
    viewer_options = st.session_state.get(BULK_ACL_VIEWER_OPTIONS_KEY)

    cols = st.columns(3)
    with cols[0]:
        _render_option_field(
            label="Legal tag name",
            session_key=BULK_LEGAL_TAG_KEY,
            options=legal_options,
            placeholder="opendes-tno-data",
            help_text=(
                "Fully qualified legal tag. Applied to every record that "
                "doesn't already carry one."
            ),
            empty_caption="⚠️ Couldn't load legal tags — enter manually",
        )
    with cols[1]:
        _render_option_field(
            label="ACL owners group",
            session_key=BULK_ACL_OWNERS_KEY,
            options=owner_options,
            placeholder="data.default.owners@opendes.dataservices.energy",
            help_text="Entitlements group that should own these records.",
            empty_caption="⚠️ Couldn't load groups — enter manually",
        )
    with cols[2]:
        _render_option_field(
            label="ACL viewers group",
            session_key=BULK_ACL_VIEWERS_KEY,
            options=viewer_options,
            placeholder="data.default.viewers@opendes.dataservices.energy",
            help_text="Entitlements group allowed to read these records.",
            empty_caption="⚠️ Couldn't load groups — enter manually",
        )


def _load_input_options(
    connection: ADMEConnection, *, force: bool = False
) -> None:
    """Autorun-once load of legal tags + entitlement groups for dropdowns."""
    if not force and st.session_state.get(BULK_OPTIONS_AUTORUN_KEY, False):
        return

    token = _acquire_token(connection)
    if token is None:
        st.session_state[BULK_OPTIONS_AUTORUN_KEY] = True
        return

    try:
        legal_result = list_legal_tags(connection, token, valid=True)
        if legal_result.ok and legal_result.items:
            names = sorted({t.name for t in legal_result.items if t.name})
            st.session_state[BULK_LEGAL_TAG_OPTIONS_KEY] = names or None
        else:
            st.session_state[BULK_LEGAL_TAG_OPTIONS_KEY] = None
    except Exception:  # noqa: BLE001
        st.session_state[BULK_LEGAL_TAG_OPTIONS_KEY] = None

    try:
        groups_result = fetch_groups(connection, token)
        owners, viewers = _partition_acl_groups(groups_result)
        st.session_state[BULK_ACL_OWNER_OPTIONS_KEY] = owners or None
        st.session_state[BULK_ACL_VIEWER_OPTIONS_KEY] = viewers or None
    except Exception:  # noqa: BLE001
        st.session_state[BULK_ACL_OWNER_OPTIONS_KEY] = None
        st.session_state[BULK_ACL_VIEWER_OPTIONS_KEY] = None

    st.session_state[BULK_OPTIONS_AUTORUN_KEY] = True


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


def _render_option_field(
    *,
    label: str,
    session_key: str,
    options: list[str] | None,
    placeholder: str,
    help_text: str,
    empty_caption: str,
) -> None:
    """Render a selectbox when options loaded; otherwise a text_input fallback."""
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
# Preview gate
# ---------------------------------------------------------------------------


def _render_preview_section(
    descriptor: DatasetDescriptor, tier_name: str
) -> None:
    """Render the Preview button + results table."""
    clicked = st.button(
        PREVIEW_BUTTON_LABEL,
        key="bulk_preview_button",
        help="Read manifests from disk, count records — no network call.",
    )

    if clicked:
        _clear_sticky_error()
        try:
            fresh_previews = preview_tier(descriptor.id, tier_name)
        except ValueError as exc:
            _set_sticky_error(f"Cannot preview {tier_name!r}: {exc}")
            st.session_state[BULK_PREVIEW_RESULTS_KEY] = []
            st.session_state[BULK_PREVIEW_SEEN_KEY] = None
            st.rerun()
            return
        st.session_state[BULK_PREVIEW_RESULTS_KEY] = fresh_previews
        st.session_state[BULK_PREVIEW_SEEN_KEY] = (descriptor.id, tier_name)
        # Reset prior submit results so the page state is coherent.
        st.session_state[BULK_SUBMIT_RESULTS_KEY] = []

    previews: list[ManifestPreview] = st.session_state.get(
        BULK_PREVIEW_RESULTS_KEY, []
    )
    seen = st.session_state.get(BULK_PREVIEW_SEEN_KEY)
    if seen != (descriptor.id, tier_name):
        return

    if not previews:
        st.caption("No manifests matched this tier's glob.")
        return

    total_records = sum(p.record_count for p in previews)
    st.success(
        f"**{len(previews)} manifests, {total_records:,} total records** "
        f"will be submitted."
    )
    frame = pd.DataFrame(
        [
            {
                "filename": p.filename,
                "kind": p.kind,
                "record_count": p.record_count,
            }
            for p in previews
        ]
    )
    st.dataframe(frame, use_container_width=True, hide_index=True)


# ---------------------------------------------------------------------------
# Submit
# ---------------------------------------------------------------------------


def _submit_disabled_reason(
    descriptor: DatasetDescriptor, tier_name: str
) -> str | None:
    """Return a human-readable reason Submit is disabled, or ``None`` when enabled."""
    seen = st.session_state.get(BULK_PREVIEW_SEEN_KEY)
    if seen != (descriptor.id, tier_name):
        return "Run Preview first to inspect manifests before submitting."
    if not str(st.session_state.get(BULK_LEGAL_TAG_KEY) or "").strip():
        return "Select a legal tag."
    if not str(st.session_state.get(BULK_ACL_OWNERS_KEY) or "").strip():
        return "Fill ACL owners group."
    if not str(st.session_state.get(BULK_ACL_VIEWERS_KEY) or "").strip():
        return "Fill ACL viewers group."
    return None


def _render_submit_section(
    connection: ADMEConnection,
    descriptor: DatasetDescriptor,
    tier_name: str,
) -> None:
    """Render the Submit button (gated) and run the loop on click."""
    disabled_reason = _submit_disabled_reason(descriptor, tier_name)
    is_disabled = disabled_reason is not None

    clicked = st.button(
        SUBMIT_BUTTON_LABEL,
        key="bulk_submit_button",
        type="primary",
        disabled=is_disabled,
        help=(
            "Sequentially submits every previewed manifest. "
            "Each result is recorded to Run History."
        ),
    )

    if is_disabled and disabled_reason is not None:
        st.caption(f"⏸️ {disabled_reason}")

    # TODO(judson): Add a mid-loop abort button once Streamlit's reactive
    # model has a cleaner cancellation primitive. For v1 the loop runs to
    # completion — to stop, close the browser tab.
    st.caption(
        "Submission runs to completion — to stop, close the browser tab."
    )

    if not clicked:
        return

    _run_submit(connection, descriptor, tier_name)


def _run_submit(
    connection: ADMEConnection,
    descriptor: DatasetDescriptor,
    tier_name: str,
) -> None:
    """Acquire a token, iterate ``submit_tier``, render progress, store results."""
    _clear_sticky_error()
    token = _acquire_token(connection)
    if token is None:
        return

    legal_tag = str(st.session_state.get(BULK_LEGAL_TAG_KEY) or "").strip()
    acl_owners = [
        str(st.session_state.get(BULK_ACL_OWNERS_KEY) or "").strip()
    ]
    acl_viewers = [
        str(st.session_state.get(BULK_ACL_VIEWERS_KEY) or "").strip()
    ]

    previews: list[ManifestPreview] = st.session_state.get(
        BULK_PREVIEW_RESULTS_KEY, []
    )
    total = len(previews)
    results: list[SubmitResult] = []

    st.write(f"Submitting {total} manifest(s)…")

    try:
        iterator = submit_tier(
            descriptor.id,
            tier_name,
            acl_owners=acl_owners,
            acl_viewers=acl_viewers,
            legal_tag=legal_tag,
            data_partition_id=connection.data_partition_id,
            connection=connection,
            token=token,
        )
        for index, result in enumerate(iterator, start=1):
            results.append(result)
            st.write(
                f"**{index} of {total}** — `{result.filename}`"
            )
            _render_submit_row(result)
    except ValueError as exc:
        _set_sticky_error(f"Submit aborted: {exc}")
        st.session_state[BULK_SUBMIT_RESULTS_KEY] = results
        st.rerun()
        return
    except Exception as exc:  # noqa: BLE001 - operator-safe summary
        _set_sticky_error(
            f"Unexpected error during submit: {type(exc).__name__}: {exc}"
        )
        st.session_state[BULK_SUBMIT_RESULTS_KEY] = results
        st.rerun()
        return

    st.session_state[BULK_SUBMIT_RESULTS_KEY] = results


def _render_submit_row(result: SubmitResult) -> None:
    """Render one ✅/❌ result row inline as it streams in."""
    if result.status == "success":
        run_label = result.run_id or "(no run id)"
        st.markdown(f"✅ `{result.filename}` → runId: `{run_label}`")
    else:
        st.markdown(
            f"❌ `{result.filename}` → {result.error or 'unknown error'}"
        )


def _render_results_section() -> None:
    """Render the persistent summary of the last submit batch."""
    results: list[SubmitResult] = st.session_state.get(
        BULK_SUBMIT_RESULTS_KEY, []
    )
    if not results:
        return

    succeeded = sum(1 for r in results if r.status == "success")
    failed = len(results) - succeeded

    st.subheader("Submit results")
    summary = f"{succeeded} of {len(results)} succeeded"
    if failed == 0:
        st.success(summary)
    else:
        st.warning(f"{summary} — {failed} failed.")

    frame = pd.DataFrame(
        [
            {
                "filename": r.filename,
                "status": r.status,
                "run_id": r.run_id or "",
                "record_id": r.record_id or "",
                "error": r.error or "",
                "submitted_at": r.submitted_at.isoformat()
                if r.submitted_at
                else "",
            }
            for r in results
        ]
    )
    st.dataframe(frame, use_container_width=True, hide_index=True)


if __name__ == "__main__":
    main()
