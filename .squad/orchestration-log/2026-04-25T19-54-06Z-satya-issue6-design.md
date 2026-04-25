# Orchestration Log: Issue #6 Design Phase

**Timestamp:** 2026-04-25T19:54:06Z  
**Issue:** #6 (Tenant-Compatible Interactive Auth)  
**Agent:** Satya (Lead)  
**Phase:** Design  

---

## Problem Statement

Interactive user auth fails in customer tenant (IPS-Energy) with AADSTS700016 error on hardcoded Azure CLI public client ID (`04b07795-a710-4f9e-9640-a91e60e60e08`). This is Microsoft's well-known first-party app for Azure CLI; some tenants block unregistered external applications via enterprise consent policies or conditional access.

The scope derivation is also wrong: current code uses `{client_id}/.default`, which builds scope from the calling app's GUID. ADME's resource identifier is `https://energy.azure.com`, not the client app ID.

---

## Root Cause Analysis

1. **Azure CLI public client blocked in tenant:** Microsoft's public-client app ID is trusted in most Azure AD tenants but not universally. Enterprise policies can restrict external app consent. IPS-Energy tenant has blocked or not consented to this app.

2. **Scope derivation incorrect:** Scope is resource-based, not client-based. Building scope from `client_id` conflates the calling app with the target service. ADME's API expects scope `https://energy.azure.com/.default` uniformly.

---

## Design Decision

### 1. Use Customer's Own App Registration

Remove hardcoded `AZURE_CLI_PUBLIC_CLIENT_ID`. Pass `connection.client_id` (user-provided in Settings) to `InteractiveBrowserCredential`.

**Why:** Customer's app registration is guaranteed to exist and be consented in their tenant. ADME admin has already configured it with:
- "Allow public client flows" enabled (required for PKCE)
- `http://localhost` redirect URI configured
- Proper API permissions assigned

No need for Microsoft's proxy app.

### 2. Hardcode ADME Scope

Replace dynamic scope property `{client_id}/.default` with constant `https://energy.azure.com/.default`.

**Why:** ADME's resource URI is constant across all customer instances. Scope identifies the *target service*, not the *calling app*. Both interactive and service-principal auth should use the same scope.

### 3. No UI Changes

Settings form already collects tenant ID and client ID. No new fields required. Scope is pure backend.

---

## Files to Change

### Backend (Kevin)
- `app/services/auth.py`
  - Remove `AZURE_CLI_PUBLIC_CLIENT_ID` constant
  - Update `_build_credential()`: pass `client_id=connection.client_id` to `InteractiveBrowserCredential`
  
- `app/models/connection.py`
  - Update `scope` property: return hardcoded `"https://energy.azure.com/.default"`

- `tests/test_auth.py`
  - Update assertions: expect `connection.client_id` (not CLI public ID)
  - Update assertions: expect scope `"https://energy.azure.com/.default"`
  - Add regression test: service principal uses same scope

- `tests/test_auth_service.py`
  - Same scope assertions

### UI (Judson)
- No changes required

### Testing (Charlie)
- Acceptance criteria and gates (separate document)

---

## Acceptance Criteria

1. Interactive browser login uses `connection.client_id`, not a hardcoded public app ID.
2. Token requests use scope `https://energy.azure.com/.default`.
3. Service principal auth remains unchanged (same client/secret/tenant, new scope).
4. All existing tests pass with updated assertions.
5. No new UI fields or form changes.
6. Code/commit message documents why hardcoded Azure CLI ID was removed.

---

## Constraints & Notes

- Customer's app must have "Allow public client flows" enabled (standard ADME requirement)
- Customer's app must have `http://localhost` redirect URI (standard ADME requirement)
- Scope is now constant—not tenant-specific, not client-specific
- Service principal remains `ClientSecretCredential` with same logic, just uses updated scope

---

## Sign-Off

**Design:** ✓ Approved (Satya)  
**Ready for Planning:** Yes  
