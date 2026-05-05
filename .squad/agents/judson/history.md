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
- 2026-05-05T14:11:09.427+02:00: Issue #8 Settings wiring keeps `ADMEConnection` static while storing pending MSAL flows and completed user auth state in explicit Streamlit session keys; callbacks are consumed once, query params are cleared, and user sign-out/auth changes clear stale health.
- 2026-05-05T15:11:17.396+02:00: Settings now exposes non-secret `Token scope` configuration, defaults it to the ADME scope, stores trimmed operator input, and treats scope-only changes as auth/health-stale connection changes.

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

## 2026-04-24 Issue #4 UI Implementation Complete
- Updated app/pages/1_⚙️_Settings.py help text: 'A browser window will open during connection test for you to sign in.'
- Removed all device-code references from UI
- Test connection flow: browser opens automatically, user signs in via standard Entra ID, control returns to app
- Success messaging: 'All X configured OSDU services responded successfully.'
- Failure messaging: 'Interactive login was cancelled. Please run Test Connection again.' (browser closed)
- Error handling: Clear messages for auth denial, network errors, headless environments
- All failure states end with consistent call-to-action: 'Run Test Connection again to retry.'
- Service principal flow unchanged
- Updated tests/test_settings_page.py with browser-workflow tests
- Added README.md operator note documenting interactive login flow
- All UI tests passing, no regressions in service-principal tests

## 2026-04-25 Issue #7 UI Guidance Update
- Root cause: Users didn't understand that new browser tab opens for interactive auth; unclear whether/where to return after sign-in
- Solution: Updated Settings page guidance text in app/pages/1_⚙️_Settings.py to explain multi-tab behavior clearly
- Changes made:
  - Updated USER_IMPERSONATION_GUIDANCE: "A new browser tab will open for Azure AD sign-in. After you complete sign-in, close that tab and return here to see the results."
  - Updated USER_IMPERSONATION_REFRESH_GUIDANCE: Same pattern for token refresh scenario
  - Explains new tab opens (sets expectation)
  - Instructs return to Streamlit after closing tab (provides clear next action)
  - Avoids technical details (localhost:8400 is implementation detail for developers)
- Why this helps: Users understand entire flow; no confusion about where results appear
- Test updates: Added UI text assertions in tests/test_settings_page.py verifying guidance contains "new browser tab" and "return here"
- Status: UI guidance implementation complete, approved for merge


## Issue #8 Auth Flow - Team Completion (2026-05-05)

**Status:** ✅ COMPLETE & VALIDATED

All team members successfully completed assigned work for MSAL auth integration:
- Satya: Lead review and final validation
- Kevin: Auth-service implementation
- Scott: Documentation and README updates
- Judson: Settings page integration
- Charlie: Quality gate and regression coverage

Final outcome: Full test suite passed (70), Ruff clean, mypy clean. Ready for merge.
## 2026-05-05: Manual Token Scope Configuration (Complete)

**Status:** COMPLETE
**Decision:** Manual token scope configuration merged to decisions.md
**Outcome:** ADMEConnection now includes token_scope field with ADME default fallback. Settings UI exposes non-secret Token scope field. Both auth paths (user and service principal) consume connection.scope. All validation passed: pytest 80, ruff, mypy.