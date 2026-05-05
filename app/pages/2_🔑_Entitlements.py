"""Entitlements smoke-test page for ADME tokens."""

from __future__ import annotations

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
    EntitlementsCallResult,
)
from app.services.auth import AuthenticationError, get_token  # noqa: E402
from app.services.entitlements import (  # noqa: E402
    fetch_groups,
    fetch_member_self,
)

SETTINGS_PAGE_PATH = "pages/1_⚙️_Settings.py"

HISTORY_KEY = "entitlements_history"
AUTORUN_KEY = "entitlements_autorun_done"
LAST_MEMBER_KEY = "entitlements_last_member"
LAST_GROUPS_KEY = "entitlements_last_groups"
HISTORY_DISPLAY_LIMIT = 20


def main() -> None:
    """Render the entitlements smoke-test page."""
    st.set_page_config(
        page_title="Entitlements · ADME Control Plane",
        page_icon="🔑",
        layout="wide",
    )
    st.title("🔑 Entitlements")
    st.markdown(
        "Verify your token works against the ADME entitlements API."
    )

    ensure_session_defaults(st.session_state)
    _ensure_page_defaults()

    connection = get_connection(st.session_state)
    if not _preflight_ok(connection):
        return
    assert connection is not None  # for mypy — _preflight_ok guarantees this

    st.caption(
        f"Data partition: `{connection.data_partition_id}` · "
        f"Endpoint: `{connection.endpoint}`"
    )

    rerun_clicked = st.button(
        "🔄 Re-run entitlements test",
        type="primary",
        key="entitlements_rerun_button",
    )

    should_run = rerun_clicked or not st.session_state.get(AUTORUN_KEY, False)
    if should_run:
        token = _acquire_token(connection)
        if token is not None:
            _run_entitlements_calls(connection, token)
            st.session_state[AUTORUN_KEY] = True

    _render_member_card(st.session_state.get(LAST_MEMBER_KEY))
    _render_groups_card(st.session_state.get(LAST_GROUPS_KEY))
    _render_history()


def _ensure_page_defaults() -> None:
    """Initialize page-scoped session keys."""
    st.session_state.setdefault(HISTORY_KEY, [])
    st.session_state.setdefault(AUTORUN_KEY, False)
    st.session_state.setdefault(LAST_MEMBER_KEY, None)
    st.session_state.setdefault(LAST_GROUPS_KEY, None)


def _preflight_ok(connection: ADMEConnection | None) -> bool:
    """Return True when we have everything required to call entitlements."""
    if connection is None or not connection.is_valid():
        st.info(
            "No ADME connection is configured for this session. "
            "Open Settings to add your endpoint, identity details, and "
            "data partition."
        )
        st.page_link(
            SETTINGS_PAGE_PATH,
            label="Open Settings",
            icon="⚙️",
        )
        return False

    if connection.auth_method == AuthMethod.USER_IMPERSONATION:
        if get_user_auth_state(st.session_state) is None:
            st.info(
                "No token available for this session. Sign in on the "
                "Settings page to enable the entitlements smoke test."
            )
            st.page_link(
                SETTINGS_PAGE_PATH,
                label="Open Settings",
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
            "Open Settings to sign in again or update credentials."
        )
        st.page_link(
            SETTINGS_PAGE_PATH,
            label="Open Settings",
            icon="⚙️",
        )
        return None
    except Exception as exc:  # noqa: BLE001 - never expose raw auth library details
        st.error(
            f"Unexpected error acquiring an ADME token: {type(exc).__name__}. "
            "Open Settings to verify your connection."
        )
        st.page_link(
            SETTINGS_PAGE_PATH,
            label="Open Settings",
            icon="⚙️",
        )
        return None


def _run_entitlements_calls(connection: ADMEConnection, token: str) -> None:
    """Call both entitlements endpoints sequentially and append history."""
    with st.spinner("Calling entitlements API…"):
        member_result = fetch_member_self(connection, token)
        _append_history(member_result)
        st.session_state[LAST_MEMBER_KEY] = member_result

        groups_result = fetch_groups(connection, token)
        _append_history(groups_result)
        st.session_state[LAST_GROUPS_KEY] = groups_result


def _append_history(result: EntitlementsCallResult) -> None:
    """Append one history entry per call. Append-only within a session."""
    history = st.session_state.get(HISTORY_KEY, [])
    history.append(
        {
            "timestamp": datetime.now(tz=UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "endpoint": result.endpoint,
            "latency_ms": round(float(result.latency_ms), 1),
            "http_status": result.http_status,
            "ok": result.ok,
        }
    )
    st.session_state[HISTORY_KEY] = history


def _render_member_card(result: EntitlementsCallResult | None) -> None:
    """Render the 'who am I?' member.self result."""
    st.subheader("Member · who am I?")
    if result is None:
        st.caption("Run the entitlements test to see results.")
        return

    if result.ok:
        identity = _identity_label(result.data)
        st.success(f"✅ Authenticated as {identity}")
        with st.expander("Raw member response"):
            st.json(result.raw_response or result.data or {})
        return

    _render_error_block(result, "Member call failed")


def _render_groups_card(result: EntitlementsCallResult | None) -> None:
    """Render the groups list result."""
    st.subheader("Groups")
    if result is None:
        st.caption("Run the entitlements test to see results.")
        return

    if result.ok:
        groups = _extract_groups(result.data)
        st.success(f"✅ Retrieved {len(groups)} groups")
        if groups:
            st.dataframe(
                _groups_to_table_rows(groups),
                use_container_width=True,
                hide_index=True,
            )
        else:
            st.caption("The response did not include any groups.")
        with st.expander("Raw groups response"):
            st.json(result.raw_response or result.data or {})
        return

    _render_error_block(result, "Groups call failed")


def _render_error_block(
    result: EntitlementsCallResult,
    headline: str,
) -> None:
    """Render the standard failure block for a failed entitlements call."""
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


def _identity_label(data: dict | None) -> str:
    """Pull a human-readable identity from the member.self response."""
    if not isinstance(data, dict):
        return "(unknown identity)"
    for key in ("email", "desId", "memberEmail", "name", "userPrincipalName"):
        value = data.get(key)
        if isinstance(value, str) and value.strip():
            return value
    return "(unknown identity)"


def _extract_groups(data: dict | None) -> list[dict[str, Any]]:
    """Pull the groups list out of the parsed response, defensively."""
    if not isinstance(data, dict):
        return []
    groups = data.get("groups")
    if not isinstance(groups, list):
        return []
    return [g for g in groups if isinstance(g, dict)]


def _groups_to_table_rows(groups: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Project group dicts into a stable column order for st.dataframe."""
    rows: list[dict[str, Any]] = []
    for group in groups:
        rows.append(
            {
                "name": _str_or_blank(group.get("name")),
                "email": _str_or_blank(group.get("email")),
                "description": _str_or_blank(group.get("description")),
            }
        )
    return rows


def _str_or_blank(value: Any) -> str:
    """Return a string representation for dataframe cells; blank for None."""
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return str(value)


def _render_history() -> None:
    """Render the latency chart, history table, and clear button."""
    st.subheader("Latency & status history")
    history: list[dict[str, Any]] = st.session_state.get(HISTORY_KEY, [])

    if not history:
        st.caption("No entitlements calls yet this session.")
        return

    chart_df = _history_to_chart_frame(history)
    if not chart_df.empty:
        st.line_chart(chart_df, y_label="latency (ms)")

    table_rows = _history_to_table_rows(history)
    st.dataframe(
        table_rows,
        use_container_width=True,
        hide_index=True,
    )

    if st.button("🧹 Clear history", key="entitlements_clear_history"):
        st.session_state[HISTORY_KEY] = []
        st.session_state[LAST_MEMBER_KEY] = None
        st.session_state[LAST_GROUPS_KEY] = None


def _history_to_chart_frame(history: list[dict[str, Any]]) -> pd.DataFrame:
    """Pivot history into a timestamp-indexed frame with one col per endpoint."""
    if not history:
        return pd.DataFrame()
    frame = pd.DataFrame(history)
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
                "latency_ms": f"{float(entry.get('latency_ms', 0.0)):.1f}",
                "http_status": (
                    entry.get("http_status")
                    if entry.get("http_status") is not None
                    else "—"
                ),
                "ok": "✅" if entry.get("ok") else "❌",
            }
        )
    return rows


if __name__ == "__main__":
    main()
