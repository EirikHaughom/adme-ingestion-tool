# Orchestration Log: Issue #7 Planning & Review Gates Phase
## Auth Redirect After Interactive Sign-In

**Phase:** Planning & Review Gates  
**Agent:** Charlie (Tester)  
**Timestamp:** 2026-04-25T21:46:41Z  
**Issue:** [#7 — Align interactive auth redirect with Streamlit app URL](https://github.com/EirikHaughom/adme-ingestion-tool/issues/7)

---

## Planning Summary

This issue addresses the UX gap where users don't know to switch back to the Streamlit tab after completing interactive authentication. The Azure SDK's `InteractiveBrowserCredential` opens a new browser tab for sign-in and waits for the authorization code on its own localhost listener (port 8400). After login, users see "Authentication complete" but don't realize they should return to Streamlit.

**Scope:** Two-part fix
1. Add explicit guidance in Settings page help text
2. Explicitly pass `redirect_uri="http://localhost:8400"` to credential for determinism

---

## Acceptance Criteria

### AC-1: Interactive Browser Auth Uses Explicit Redirect URI
**Given** a user initiates "Test Connection" with USER_IMPERSONATION auth  
**When** the auth flow initializes the credential  
**Then** `InteractiveBrowserCredential` must be initialized with an explicit redirect_uri parameter  
**And** the value must match the app registration (http://localhost:8400)  
**And** the flow must complete without breaking token acquisition

### AC-2: Settings Page Guidance Reflects Implemented Behavior
**Given** the Settings page is displayed for USER_IMPERSONATION auth  
**When** the user reads on-screen help text  
**Then** guidance must clearly indicate a new browser tab will open for sign-in  
**And** text must instruct user to close the tab and return to Streamlit after login  
**And** no mention of localhost:8400 in user-facing text (implementation detail)

### AC-3: Token Acquisition & Session Storage Unaffected
**Given** auth redirect behavior is modified  
**When** interactive auth completes  
**Then** the access token must be successfully captured and returned  
**And** session state must be correctly populated for OSDU service calls

### AC-4: Tenant-Aware Auth Behavior Preserved
**Given** the app supports multiple Azure tenants  
**When** interactive auth is triggered with a specific tenant ID  
**Then** `tenant_id` must be correctly passed to credential  
**And** redirect behavior must not break multi-tenant support

---

## Reviewer Gates

### Gate-R1: Redirect URI Configuration Verification
**Check:** Reviewer confirms explicit redirect_uri is passed to InteractiveBrowserCredential.
- [ ] Code shows `redirect_uri="http://localhost:8400"` or constant in interactive credential init
- [ ] Value matches app registration
- [ ] ClientSecretCredential behavior is unchanged
- **Acceptance:** Code clearly documents why this port is used

### Gate-R2: Settings Page Guidance Audit
**Check:** Reviewer verifies help text is accurate and consistent.
- [ ] `USER_IMPERSONATION_GUIDANCE` explains new browser tab and return to Streamlit
- [ ] `USER_IMPERSONATION_REFRESH_GUIDANCE` is updated if applicable
- [ ] No stale references to callback URLs or device code flow
- **Acceptance:** All help text updated; user experience matches text description

### Gate-R3: Test Coverage for Redirect Behavior
**Check:** Reviewer confirms adequate test coverage.
- [ ] Unit tests verify the interactive credential receives redirect_uri parameter
- [ ] Token acquisition still works after redirect_uri changes
- [ ] Error message audits confirm no unwanted localhost:8400 references
- **Acceptance:** Test suite passes; coverage maintained or improved

### Gate-R4: Multi-Tenant Compatibility Validation
**Check:** Reviewer confirms no cross-tenant auth confusion.
- [ ] `tenant_id` is correctly passed to credential
- [ ] Redirect URI does not hardcode tenant-specific values
- [ ] Session state isolation by tenant is preserved
- **Acceptance:** Architecture review confirms no token leakage risk

### Gate-R5: No Regressions in Service Principal Flow
**Check:** Reviewer verifies ClientSecretCredential is unaffected.
- [ ] Service principal auth still works without changes
- [ ] No unintended scope or client ID modifications
- **Acceptance:** Service principal tests pass without modification

---

## Test Coverage Strategy

### Unit Tests (Required)
- ✅ **Existing:** `test_get_token_uses_configured_browser_client_for_user_impersonation` must pass
- ✅ **Existing:** `test_user_impersonation_auth_error_messages_exclude_device_code_language` validates message cleanliness
- ⭐ **New/Updated:** Assert that `redirect_uri="http://localhost:8400"` is passed to credential kwargs

### Integration Tests (Recommended)
- 🔍 **Consider:** Validate Settings page form submission → auth → token acquisition flow
- 🔍 **Consider:** Verify Streamlit session state is correctly populated after auth

### Manual/E2E Verification (Required)
- 👤 **Manual test:** Launch app locally, navigate to Settings, use USER_IMPERSONATION, verify browser opens new tab and closes cleanly after login
- 👤 **Manual test:** Verify service validation results appear in Settings page without manual browser navigation
- 👤 **Manual test:** Test with multiple tenants; confirm no auth mixing

---

## Definition of Done

- [ ] Explicit `redirect_uri="http://localhost:8400"` added to InteractiveBrowserCredential in `app/services/auth.py`
- [ ] Settings page help text updated and audited
- [ ] All unit tests pass (existing and new)
- [ ] All reviewer gates (R1–R5) approved
- [ ] Manual E2E test completed and documented in PR
- [ ] No regressions in service principal (CLIENT_SECRET) auth flow
- [ ] GitHub issue #7 updated with implementation status

---

## Risk Assessment

| Risk | Likelihood | Mitigation |
|------|------------|-----------|
| Redirect URI causes token loss | Low | Comprehensive test coverage + manual E2E test before merge |
| Help text becomes stale again | Low | Include documentation update in PR definition of done |
| Multi-tenant confusion | Low | Explicit tenant_id passing already validated in prior issues |
| Port conflict on localhost:8400 | Low | Document operator responsibility; note in README |

---

## Sign-Off

✅ **Planning & test gate approval for implementation phase**

Next: Kevin implements backend changes; Judson updates Settings page guidance.
