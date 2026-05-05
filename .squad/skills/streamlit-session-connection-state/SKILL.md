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
- Keep OAuth pending flows and completed user auth state in separate session keys; clear both on sign-out or connection/auth-method change.
- Consume OAuth callback query params once, exchange only when a pending flow exists, and clear query params in a `finally` path to prevent rerun replay.
- In callback-failure tests, distinguish the stale pending flow from any newly generated retry flow; assert the old flow is not reused after missing-pending, denial, state-mismatch, or token-exchange failures.
- Clear stale health whenever completed user auth state changes so service validation never reflects a prior signed-in identity.
- Treat non-secret auth configuration changes, including token scope, as connection changes so pending user auth, completed user auth, and stale health are cleared before validation.
- Convert dataclass results into plain table rows before rendering to keep the UI layer simple and testable.
- When a session is unconfigured or unvalidated, show the next step immediately with a direct Settings page link.

## Examples
- `app\connection_state.py`
- `app\main.py`
- `app\pages\1_⚙️_Settings.py`

## Anti-Patterns
- Persisting `client_secret` beyond the active Streamlit session
- Reusing old health results after endpoint, tenant, partition, or auth settings change
- Replaying OAuth callback query params across Streamlit reruns
- Treating "some pending flow exists" as proof stale OAuth state was cleared
- Storing authorization codes, pending flow payloads, tokens, or MSAL caches on static connection models
- Making operators hunt for the Settings page when no connection is configured
- Mixing auth failures into the service table instead of surfacing a dedicated error state
