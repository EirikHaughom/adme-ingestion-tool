---
name: streamlit-session-connection-state
description: Keep Streamlit connection flows explicit, session-scoped, and operator-readable
domain: streamlit, state-management
confidence: high
source: earned (issue #2 welcome/settings implementation)
---

## Context
Use this pattern when a Streamlit app collects connection details on one page and needs to surface the current status on another page without persisting secrets.

## Patterns
- Store the active connection, latest validation results, and latest validation error in separate `st.session_state` keys.
- Keep `client_secret` in session state only; never write it to committed files or long-lived config.
- Clear prior validation results when saved connection details change so the landing page never shows stale health.
- Convert dataclass results into plain table rows before rendering to keep the UI layer simple and testable.
- When a session is unconfigured or unvalidated, show the next step immediately with a direct Settings page link.

## Examples
- `app\connection_state.py`
- `app\main.py`
- `app\pages\1_⚙️_Settings.py`

## Anti-Patterns
- Persisting `client_secret` beyond the active Streamlit session
- Reusing old health results after endpoint, tenant, partition, or auth settings change
- Making operators hunt for the Settings page when no connection is configured
- Mixing auth failures into the service table instead of surfacing a dedicated error state
