# Project Context

- **Owner:** Eirik Haughom
- **Project:** Streamlit control plane app for Azure Data Manager for Energy (ADME)
- **Stack:** Python, Streamlit, Azure, ADME/OSDU APIs
- **Created:** 2026-04-24

## Learnings

- Judson owns Streamlit pages, operator workflows, and user-facing control-plane behavior.
- The app should make ADME operations visible, actionable, and easy to navigate for operators.
- 2026-04-24T14:38:18.059+02:00: `app\main.py` is now the welcome page, `app\pages\1_⚙️_Settings.py` owns ADME connection setup, and both pages share state through `app\connection_state.py`.
- 2026-04-24T14:38:18.059+02:00: Operator-facing connection flow should save valid settings, clear stale health results when settings change, and keep `client_secret` only in Streamlit session state.
- 2026-04-24T14:38:18.059+02:00: ADME validation depends on `app\services\auth.py`, `app\services\health.py`, and the canonical `OSDU_SERVICES` list in `app\models\connection.py`, including the EDS probe.
- 2026-04-24T14:38:18.059+02:00: UI review gates for issue #2 are best protected with page tests that assert the exact field contract, auth-method field gating, masked `client_secret`, and matrix rendering for degraded service results.

## 2026-04-24 Issue #2 Implementation Complete
- Implemented welcome page in app/main.py (landing, connection status summary)
- Implemented settings page in app/pages/1_⚙️_Settings.py (form, health validation button, matrix rendering)
- Session-state connection UX: saves valid settings, clears stale health on config change, keeps client_secret session-scoped only
- Conditional client_secret field visibility based on auth_method (DeviceCodeCredential vs ClientSecretCredential)
- Service-by-service health matrix rendering (deterministic OSDU_SERVICES order)
- UI tests using Streamlit recorder pattern, auth-mode field gating tests, health matrix rendering tests
- Integrated with Kevin's auth.py:get_token() and health.py:check_all() services
- All acceptance criteria met, ready for Charlie's final review

## 2026-04-24 Issue #3 Streamlit Import-Path Fix Complete
- Fixed multipage import-path failure: Streamlit executes page scripts from their directory, omitting repository root from sys.path
- Solution: Prepend repository root to sys.path at top of app/main.py and app/pages/1_⚙️_Settings.py before local imports
- Minimal 4-line bootstrap, idempotent (checks before inserting), keeps existing app/ structure intact
- Absolute app.* imports remain unchanged (no style shift)
- Added tests/test_streamlit_import_paths.py: subprocess-based regression tests simulating Streamlit-style script loading for both entry point and pages
- Verified all app.* imports resolve correctly in isolated subprocess environment
- Prevents silent reversion to failing state
- All validation clean: pytest passing, ruff clean, mypy clean
- Issue #3 updated with real implementation status
