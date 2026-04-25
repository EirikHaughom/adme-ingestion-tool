# Orchestration Log: Issue #6 Planning Phase

**Timestamp:** 2026-04-25T20:04:12Z  
**Issue:** #6 (Tenant-Compatible Interactive Auth)  
**Agent:** Charlie (Tester)  
**Phase:** Planning → Acceptance Criteria & Reviewer Gates  

---

## Planning Summary

Satya's design approved. Moving to detailed acceptance criteria and reviewer gate specifications for implementation and final review.

---

## Acceptance Criteria

### AC1: Interactive User Auth Succeeds in IPS-Energy Tenant
**Given** a user configures the tool with:
- Tenant ID: IPS-Energy tenant GUID
- Client ID: The configured ADME app registration ID  
- Auth method: User Impersonation
- Any valid ADME endpoint

**When** the user clicks "Test Connection"

**Then**
- A browser window opens for interactive sign-in
- User authenticates successfully in their tenant
- No AADSTS700016 error appears
- An access token is acquired
- Health check proceeds successfully (or fails with service-level errors, not auth errors)

### AC2: Scope Is Updated to Energy.Azure.Com
**Given** the connection model is configured with a client ID

**When** `connection.scope` is accessed

**Then** it returns `https://energy.azure.com/.default`

**And** NOT `<client_id>/.default` (the old behavior)

### AC3: Service Principal Auth Remains Unaffected
**Given** a user configures service principal authentication (unchanged auth method)

**When** the user clicks "Test Connection"

**Then**
- Client secret credential is used (unchanged)
- Token acquisition works exactly as before
- Scope is also `https://energy.azure.com/.default`
- No regression in service principal behavior

### AC4: Hardcoded App ID Origin Is Documented
**Given** code or documentation review

**When** a reviewer examines the implementation

**Then** there is clear documentation or a commit comment explaining:
- Where the Azure CLI public client ID comes from (if still used)
- Why it is/is not suitable for the tenant-compatible fix
- What the real approach is (using customer's own app registration)

---

## Reviewer Gates (Pre-Merge Checks)

### Gate 1: No Hardcoded App IDs Without Justification
**Check:**
- If the hardcoded `AZURE_CLI_PUBLIC_CLIENT_ID` is removed, confirm deletion is intentional
- If it remains, verify there is a comment or decision document explaining why
- Confirm there is NO new hardcoded app ID that bypasses the customer's tenant

**Pass Condition:**
- Either removed cleanly, or documented with clear rationale

### Gate 2: Scope Configuration Is Correct
**Check:**
- Trace the scope value end-to-end:
  - Where is `https://energy.azure.com/.default` set?
  - Is it in the connection model, auth module, or both?
  - Confirm it is NOT `<client_id>/.default` anymore
- Verify both auth methods (user impersonation and service principal) use the new scope
- Check that scope is passed correctly to `credential.get_token(scope)`

**Pass Condition:**
- Scope is hardcoded to `https://energy.azure.com/.default`
- Used for both auth methods
- Tests verify the scope value

### Gate 3: Client ID Strategy Is Clear
**Check:**
- Confirm customer's `client_id` is used in InteractiveBrowserCredential
- Verify this removes dependency on Microsoft's Azure CLI public app
- Ensure no fallback to hardcoded app ID exists

**Pass Condition:**
- Customer app registration used for interactive auth
- Clear explanation why Azure CLI public ID was removed

### Gate 4: Tests Cover the New Auth Behavior
**Check:**
- Unit tests verify:
  - User impersonation passes correct client ID, tenant ID, and scope to credential builder
  - Service principal is unchanged
  - Scope value is exactly `https://energy.azure.com/.default`
- Error handling tests verify:
  - AADSTS errors are formatted correctly in the UI
  - Auth error messages don't expose implementation details
- Existing tests still pass (no regression)

**Pass Condition:**
- All existing tests pass
- New or updated tests cover the scope change and auth method behavior
- Test names and assertions are clear

### Gate 5: Regression Test Coverage
**Check:**
- Auth error messages for user impersonation still exclude device-code language
- Service principal error messages are preserved
- Health check page still displays auth errors clearly
- Settings page still accepts and persists auth method and credentials correctly
- No token caching or stale token issues from the scope change

**Pass Condition:**
- All existing auth error message tests pass
- All existing health check tests pass
- Settings page tests pass
- No regressions detected

---

## Expected Test Updates

### Unit Tests (test_auth.py)
- Update scope assertion in `test_get_token_uses_public_browser_client_for_user_impersonation`:
  - Old: `assert calls["scope"] == "client-id/.default"`
  - New: `assert calls["scope"] == "https://energy.azure.com/.default"`
  
- Update scope assertion in `test_get_token_uses_client_secret_credential`:
  - Same change as above

- Verify (no changes needed):
  - `test_user_impersonation_auth_error_messages_exclude_device_code_language`
  - `test_get_token_preserves_service_principal_error_message`

### Integration Tests
- Settings page tests still pass (form submission, validation)
- Connection test flow still works
- No UI regressions

---

## Test Execution Plan

1. **Run baseline tests** → All tests pass before implementation
2. **Implement the fix** → Kevin updates auth.py and connection.py
3. **Update assertions** → Scope value in tests changes to `https://energy.azure.com/.default`
4. **Run full test suite** → All tests pass (including updated unit tests)
5. **Manual smoke test** → Verify interactive auth with real Azure AD tenant (if available)
6. **Update issue** → Confirm AC1–AC4 are met, link PR to issue

---

## Sign-Off

**Planning:** ✓ Approved (Charlie)  
**Ready for Implementation:** Yes  
**Reviewer Gates:** Ready (Charlie as tester + code reviewer)  
