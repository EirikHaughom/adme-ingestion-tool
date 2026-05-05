"""Entry point for the ADME control plane Streamlit app."""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if PROJECT_ROOT not in {Path(path or ".").resolve() for path in sys.path}:
    sys.path.insert(0, str(PROJECT_ROOT))

import streamlit as st  # type: ignore[import-not-found]  # noqa: E402

from app.connection_state import (  # noqa: E402
    ensure_session_defaults,
    format_auth_method,
    format_overall_state,
    get_connection,
    get_health_error,
    get_health_results,
    get_overall_state,
    results_to_table_rows,
    summarize_health,
)

SETTINGS_PAGE_PATH = "pages/1_⚙️_Settings.py"
ENTITLEMENTS_PAGE_PATH = "pages/2_🔑_Entitlements.py"


def main() -> None:
    st.set_page_config(
        page_title="ADME Control Plane",
        page_icon="⚡",
        layout="wide",
    )
    st.title("ADME Control Plane")
    st.markdown(
        "Connect an Azure Data Manager for Energy instance, validate core "
        "OSDU services, and keep operators on the shortest path to action."
    )
    st.page_link(
        SETTINGS_PAGE_PATH,
        label="Open Settings",
        icon="⚙️",
    )
    st.page_link(
        ENTITLEMENTS_PAGE_PATH,
        label="Open Entitlements smoke test",
        icon="🔑",
    )

    ensure_session_defaults(st.session_state)
    connection = get_connection(st.session_state)
    overall_state = get_overall_state(st.session_state)

    st.subheader("Connection state")
    st.markdown(f"**Status:** {format_overall_state(overall_state)}")
    st.caption("Need to change this session's connection? Open Settings.")

    if connection is None or overall_state == "not_configured":
        st.warning("No ADME connection is configured for this session.")
        st.info(
            "Go to Settings to add your ADME endpoint, identity details, "
            "data partition, and validation workflow."
        )
        return

    st.subheader("Current session connection")
    st.markdown(
        "\n".join(
            [
                f"- **Endpoint:** `{connection.endpoint}`",
                f"- **Data partition:** `{connection.data_partition_id}`",
                f"- **Auth method:** {format_auth_method(connection.auth_method)}",
                f"- **Tenant ID:** `{connection.tenant_id}`",
                f"- **Client ID:** `{connection.client_id}`",
            ]
        )
    )

    health_error = get_health_error(st.session_state)
    if health_error:
        st.error(f"Last connection test failed: {health_error}")
        st.info("Update the settings and run Test Connection again.")
        return

    health_results = get_health_results(st.session_state)
    health_summary = summarize_health(health_results)
    if overall_state == "not_tested":
        st.info(
            "Connection settings are saved for this session, but the ADME "
            "services have not been validated yet."
        )
        return

    if overall_state == "healthy":
        st.success(
            f"All {health_summary.total_services} configured OSDU services "
            "responded successfully."
        )
    elif overall_state == "degraded":
        st.warning(
            f"{health_summary.unhealthy_services} service(s) need attention."
        )
    else:
        st.error(
            f"{health_summary.error_services} service probe(s) failed before a "
            "response was returned."
        )

    st.subheader("Latest service health")
    st.dataframe(
        results_to_table_rows(health_results),
        use_container_width=True,
        hide_index=True,
    )


if __name__ == "__main__":
    main()
