# Charlie Orchestration Log — Issue #5 Planning Batch

## Agent Status
- **Role:** Tester
- **Mode:** Planning (reviewer gates & test strategy)
- **Issue:** #5
- **Timestamp:** 2026-04-25T19:44:06.175+02:00

## Outcome
Defined comprehensive acceptance criteria, review gates, and test strategy for interactive auth callback fix. All gates are implementable; no blockers identified.

## Acceptance Criteria

### Browser Sign-In → Token Exchange
✓ Browser opens on user's machine
✓ User completes Azure AD sign-in
✓ Auth code returned to localhost callback
✓ Token exchange succeeds without AADSTS7000218
✓ Token's `aud` claim matches ADME resource ID (from scope derivation)
✓ Service principal auth remains unchanged

### Settings Page Workflow
✓ Settings → Create/Edit Connection → USER_IMPERSONATION
✓ User saves connection, Tests Connection, browser opens
✓ Browser sign-in completes successfully
✓ Settings page displays **green validation summary**
✓ Success state persists to next page reload
✓ Error states (canceled browser, blocked) show inline guidance

### Error Handling
✗ No AADSTS7000218 errors (public client ID fix)
✗ CredentialUnavailableError caught, message adapted to browser flow
✗ Canceled/blocked browser flow returns clear operator guidance
✗ Headless environments fail gracefully (not in scope for #5, covered by #4)

## Reviewer Gates

**Mandatory approvals before merge:**
1. **Code reviewer:** Auth flow change (public client ID substitution, scope preservation)
   - Verify Azure CLI client ID constant is correct
   - Verify scope derivation still uses connection.client_id
   - Verify service principal auth unchanged
2. **Test reviewer:** Test coverage for callback success and error paths
   - Unit test: public client ID asserted
   - Unit test: AADSTS7000218 scenario (public vs confidential confusion)
   - Integration test: full Settings → TestConnection → browser flow
   - Integration test: error handling (cancelled browser, unavailable)
   - Regression test: service principal auth still works
3. **Integration reviewer:** End-to-end Settings flow in test environment
   - Settings page workflow covers user impersonation save, test, browser flow
   - Green validation summary renders
   - No device-code language in errors
4. **Code coverage:** >=90% for auth module (continuation from #4)

## Test Strategy

### Unit Tests (`tests/test_auth.py`)
- `test_build_credential_interactive_uses_public_client_id()`: Assert Azure CLI client ID
- `test_build_credential_service_principal_unchanged()`: Assert ClientSecretCredential still used
- `test_build_credential_scope_derivation()`: Verify scope uses connection.client_id
- `test_credential_callback_aadsts7000218_explanation()`: Mock AADSTS7000218 response, verify error message clarity

### Integration Tests (`tests/test_auth_service.py`)
- `test_auth_service_interactive_token_acquisition()`: Mock browser flow with real callback, assert token scope
- `test_auth_service_interactive_browser_cancelled()`: Simulate user cancellation, verify error handling
- `test_auth_service_service_principal_regression()`: Verify service principal unchanged, token valid
- `test_auth_service_scope_resolution()`: Verify token audience matches connection.client_id

### Regression Tests (same suite)
- `test_app_pages_settings_workflow_interactive()`: Full Settings → TestConnection UI flow (selenium/playwright mock)
- `test_app_pages_settings_success_state()`: Green validation summary after successful browser sign-in

## Implementation Expectations

**Backend (Kevin):**
- Define AZURE_CLI_PUBLIC_CLIENT_ID constant
- Update _build_credential() for USER_IMPERSONATION path only
- Update auth.py test assertions
- Update auth_service.py test assertions

**Frontend (Judson, optional):**
- No UI changes needed (Settings page already refers to "browser sign-in")
- Verify error messages don't reference device codes (Charlie's #4 work)

## Dependencies
- Depends on successful closure of issue #4 (error message cleanup)
- Service principal auth must remain regression-free

## Status
✓ Gates defined — ready for implementation review
