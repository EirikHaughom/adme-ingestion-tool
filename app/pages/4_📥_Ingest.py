"""Ingest landing page for ADME.

Lightweight chooser that points operators at the available ingestion
methods (manifest, single-file upload, future CSV). Pre-flight chain
mirrors the other Operate pages so the operator sees a consistent
"connect first" prompt before being offered the method cards.
"""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if PROJECT_ROOT not in {Path(path or ".").resolve() for path in sys.path}:
    sys.path.insert(0, str(PROJECT_ROOT))

import streamlit as st  # type: ignore[import-not-found]  # noqa: E402

from app.connection_state import (  # noqa: E402
    ensure_session_defaults,
    get_connection,
    get_user_auth_state,
)
from app.models.connection import ADMEConnection, AuthMethod  # noqa: E402

SETTINGS_PAGE_PATH = "pages/1_⚙️_Instance_Configuration.py"
MANIFEST_PAGE_PATH = "pages/5_📄_Manifest.py"
FILE_PAGE_PATH = "pages/6_📂_File.py"


def main() -> None:
    """Render the Ingest landing / chooser page."""
    st.set_page_config(
        page_title="Ingest · ADME Control Plane",
        page_icon="📥",
        layout="wide",
    )
    st.title("📥 Ingest data into ADME")
    st.markdown(
        "Pick how you want to load data. Each method writes to your ADME "
        "instance through the corresponding OSDU service."
    )

    ensure_session_defaults(st.session_state)

    connection = get_connection(st.session_state)
    if not _preflight_ok(connection):
        return
    assert connection is not None  # mypy — _preflight_ok guarantees this

    st.caption(
        f"Data partition: `{connection.data_partition_id}` · "
        f"Endpoint: `{connection.endpoint}`"
    )

    _render_method_cards()
    _render_help_expander()


# ---------------------------------------------------------------------------
# Pre-flight
# ---------------------------------------------------------------------------


def _preflight_ok(connection: ADMEConnection | None) -> bool:
    """Return True when the session has a usable ADME connection."""
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
                "Instance Configuration page to enable ingestion."
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


# ---------------------------------------------------------------------------
# Method chooser
# ---------------------------------------------------------------------------


def _render_method_cards() -> None:
    """Render three side-by-side method cards."""
    st.subheader("Choose a method")

    manifest_col, file_col, csv_col = st.columns(3, gap="large")

    with manifest_col:
        st.markdown("### 📄 Manifest")
        st.markdown(
            "Submit a JSON manifest via the Workflow Service. Best for "
            "reference data and pre-built manifests."
        )
        st.page_link(
            MANIFEST_PAGE_PATH,
            label="Open Manifest ingestion",
            icon="📄",
        )

    with file_col:
        st.markdown("### 📂 File")
        st.markdown(
            "Upload a file and register it as a Storage record. Best for "
            "individual data files."
        )
        st.page_link(
            FILE_PAGE_PATH,
            label="Open File upload",
            icon="📂",
        )

    with csv_col:
        st.markdown("### 📊 CSV")
        st.caption("Coming soon")
        st.markdown(
            ":grey[Bulk-load tabular data from a CSV. Not yet available.]"
        )


def _render_help_expander() -> None:
    """Render a short 'when to use which' explainer."""
    with st.expander("What's the difference?"):
        st.markdown(
            "- **📄 Manifest** — you already have an OSDU manifest JSON "
            "(or want to use a curated sample). The Workflow Service "
            "validates it, creates the records, and you can poll the run "
            "status.\n"
            "- **📂 File** — you have a single data file (PDF, LAS, "
            "image, etc.). The File Service issues a signed URL, you push "
            "the bytes to Azure Blob, then register the file metadata. "
            "Returns a record id you can reference from a manifest.\n"
            "- **📊 CSV** — bulk-load tabular data. Coming soon."
        )


if __name__ == "__main__":
    main()
