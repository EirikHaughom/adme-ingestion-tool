# Charlie Orchestration Log — Issue #4 Planning Batch

## Agent Status
- **Role:** Tester
- **Mode:** Planning
- **Issue:** #4
- **Timestamp:** 2026-04-24T19:54:00.751+02:00

## Outcome
Defined acceptance criteria and reviewer gates for the interactive-login change, including browser-sign-in guidance, retry messaging, regression coverage expectations, and headless-environment caveats. Updated issue #4 with the real planning status.

## Acceptance Criteria

### 1. Authentication Behavior (MUST)
- When `auth_method == AuthMethod.USER_IMPERSONATION`, instantiate `InteractiveBrowserCredential` (not `DeviceCodeCredential`)
- Call with `client_id` and `tenant_id` from connection
- Remove `_device_code_prompt_callback` mechanism
- Token acquisition still requests scope `{client_id}/.default`
- Credential properly closed after use via existing `_close_credential()` pattern
- Service principal auth remains unchanged (`ClientSecretCredential`)
- Auth failures wrapped in `AuthenticationError` with descriptive messages (no device-code exposure)

### 2. UI/Help Text (MUST)
- Settings page displays: "A browser window will open during connection test for you to sign in."
- Remove all references to device codes, manual code entry, or https://login.microsoft.com/device
- When "Test Connection" clicked with user impersonation, browser opens automatically
- After successful auth, connection test proceeds to health probes
- If browser closes without authentication: "Interactive login was cancelled. Please run Test Connection again."
- Main page does NOT show device-code instructions in any error messages
- Health check failures related to auth clearly state: "Re-run Test Connection to re-authenticate"

### 3. Test Coverage (MUST)
- Unit test: `test_get_token_uses_interactive_browser_credential_for_user_impersonation`
  * Verify credential instantiation with correct tenant_id and client_id
  * Verify credential's `get_token(scope)` called and returns valid token
  * Verify credential closed after use
  * Verify NO prompt callback registered
- Unit test: `test_device_code_prompt_callback_not_used_for_user_impersonation`
  * Verify `_device_code_prompt_callback` is deleted or not passed for user impersonation
- Unit test: `test_user_impersonation_auth_error_messages_exclude_device_code_language`
  * Simulate auth failures (ClientAuthenticationError, CredentialUnavailableError)
  * Verify error messages do NOT contain "device code", "login.microsoft.com/device"
  * Verify messages guide users to "run Test Connection again"
- Integration test: `test_connection_test_button_with_user_impersonation_opens_browser`
  * Mock InteractiveBrowserCredential, simulate successful login
  * Verify health probes called after auth succeeds
  * Verify success message shown
- Integration test: `test_connection_test_fails_gracefully_when_interactive_login_cancelled`
  * Mock credential to raise CredentialUnavailableError
  * Verify Streamlit displays cancellation message
  * Verify session state does NOT save partial/invalid token
- Settings page regression test: `test_settings_page_user_impersonation_shows_browser_login_guidance`
  * Verify "User Impersonation" displays browser login guidance
  * Verify service principal shows secret guidance (unchanged)

## Reviewer Gates

**Gate 1: Credential Replacement**
- DeviceCodeCredential import removed/unused
- InteractiveBrowserCredential imported from azure.identity
- _build_credential() returns InteractiveBrowserCredential for user impersonation
- Call signature matches azure-identity v1.19+ API
- All existing tests for service principal still pass

**Gate 2: Error Handling & Messages**
- No "device code" language in auth.py
- Error messages use "Interactive login required" or "Browser authentication failed"
- _close_credential() called correctly on InteractiveBrowserCredential
- AuthenticationError provides actionable guidance

**Gate 3: UI/UX Alignment**
- Settings page no longer shows device-code instructions
- Settings page displays: "A browser window will open during connection test for you to sign in."
- Test connection success path works end-to-end
- Test connection failure path shows browser cancellation message
- Main page does NOT reference device codes

**Gate 4: Test Coverage**
- New unit tests for InteractiveBrowserCredential instantiation pass
- Old unit test for DeviceCodeCredential removed/rewritten
- No "device code" language in test expectations
- At least one integration test confirms Streamlit workflow end-to-end
- pytest --cov=app shows auth.py at ≥90% coverage
- All existing tests still pass (no regressions)

**Gate 5: Headless Environment Fallback (SHOULD)**
- Document behavior in headless/non-interactive environments
- InteractiveBrowserCredential raises CredentialUnavailableError (handled gracefully)
- Users in headless mode see: "Interactive login is not available in headless mode. Switch to service principal auth."

## Status
✓ Planning complete — ready for implementation
