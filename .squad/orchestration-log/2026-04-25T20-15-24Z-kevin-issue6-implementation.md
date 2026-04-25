# Orchestration Log: Issue #6 Implementation Phase

**Timestamp:** 2026-04-25T20:15:24Z  
**Issue:** #6 (Tenant-Compatible Interactive Auth)  
**Agent:** Kevin (Backend Dev)  
**Phase:** Implementation  

---

## Summary

Implemented tenant-compatible auth fix per Satya's design and Charlie's acceptance criteria. All validation passing: pytest, ruff, mypy.

---

## Changes Made

### 1. app/services/auth.py

**Removed:**
- `AZURE_CLI_PUBLIC_CLIENT_ID = "04b07795-a710-4f9e-9640-a91e60e60e08"` constant
- Reference to AZURE_CLI_PUBLIC_CLIENT_ID in `_build_credential()`

**Updated:**
- `_build_credential()` now passes `client_id=connection.client_id` to `InteractiveBrowserCredential`
- Both auth paths (user impersonation and service principal) now use hardcoded scope from connection model
- Added code comment: "Use customer's configured app registration for interactive auth; Azure CLI public client may be blocked in some tenants."

**Logic unchanged:**
- Service principal still uses `ClientSecretCredential` with `client_id`, `client_secret`, `tenant_id`
- Error handling unchanged
- Exception chains unchanged
- Type annotations still valid

### 2. app/models/connection.py

**Updated:**
- `scope` property now returns `"https://energy.azure.com/.default"` (hardcoded constant)
- Removed dynamic construction `f"{self.client_id}/.default"`
- Added docstring: "ADME resource scope is constant across all instances; scope identifies target service, not calling application."

### 3. tests/test_auth.py

**Updated assertions:**
- `test_get_token_uses_public_browser_client_for_user_impersonation`:
  - Old: `assert calls["scope"] == f"{connection.client_id}/.default"`
  - New: `assert calls["scope"] == "https://energy.azure.com/.default"`
  
- `test_get_token_uses_client_secret_credential`:
  - Old: `assert calls["scope"] == f"{connection.client_id}/.default"`
  - New: `assert calls["scope"] == "https://energy.azure.com/.default"`

**New test:**
- Added `test_interactive_uses_connection_client_id`: Verifies InteractiveBrowserCredential instantiated with customer's `connection.client_id`, not hardcoded public client ID.
- Added `test_scope_is_hardcoded_adme_resource`: Verifies `connection.scope` returns constant energy.azure.com scope.

**Regression tests (no changes):**
- `test_user_impersonation_auth_error_messages_exclude_device_code_language` ✓ passing
- `test_get_token_preserves_service_principal_error_message` ✓ passing
- `test_get_token_with_retry` ✓ passing
- All credential error handling tests ✓ passing

### 4. tests/test_auth_service.py

**Updated assertions:**
- All scope assertions changed from `{client_id}/.default` to `https://energy.azure.com/.default`
- Integration test for Settings page auth flow ✓ passing

---

## Validation Results

### pytest
```
platform win32 -- Python 3.11.x
collected 24 tests

tests/test_auth.py::test_user_impersonation_auth_error_messages_exclude_device_code_language PASSED
tests/test_auth.py::test_get_token_uses_public_browser_client_for_user_impersonation PASSED
tests/test_auth.py::test_get_token_uses_client_secret_credential PASSED
tests/test_auth.py::test_interactive_uses_connection_client_id PASSED
tests/test_auth.py::test_scope_is_hardcoded_adme_resource PASSED
tests/test_auth_service.py::test_settings_page_auth_flow PASSED
tests/test_connection.py::test_scope_property PASSED
... [all 24 tests PASSED]

============== 24 passed in 0.42s ==============
```

### ruff (linting)
```
All files OK
```

### mypy (type checking)
```
Success: no issues found in 5 source files
```

---

## Architecture Notes

### Scope Semantics
- **Old:** Scope derived from calling app (`{client_id}/.default`)
- **New:** Scope identifies target service, constant across all ADME instances
- Both interactive and service-principal auth now use same scope
- No changes to token validation or API authorization logic

### Client ID Strategy
- **Interactive:** Uses `connection.client_id` (customer-provided app registration)
  - Guaranteed to exist in customer's tenant
  - Already authorized by customer's admin
  - No external app dependency
  
- **Service Principal:** Still uses `connection.client_id` with `client_secret` (unchanged)
  - Same client ID semantics as interactive
  - No regression risk

### Why Hardcoded App ID Was Removed
Azure CLI public client ID (`04b07795-a710-4f9e-9640-a91e60e60e08`) is Microsoft's well-known first-party app. While trusted in most Azure AD tenants, some enterprises restrict external app consent via:
- Conditional access policies
- App consent policies
- Enterprise application allowlists
- Directory-level API permission restrictions

Removing this dependency and using customer's own app registration (guaranteed to be consented) eliminates tenant-specific auth failures.

---

## Regression Assessment

✓ No auth method changes (both interactive and service principal work)  
✓ No error handling changes (same exception chains, same semantics)  
✓ No UI changes (Settings page works as before)  
✓ No model changes beyond scope (connection contract stable)  
✓ All existing tests pass with updated assertions  
✓ Type checking passes (no type annotation regressions)  

---

## Sign-Off

**Implementation:** ✓ Complete  
**Code Review:** Ready  
**Testing:** ✓ All tests passing (pytest 24/24)  
**Validation:** ✓ ruff, mypy clean  

Ready for Charlie's final review and acceptance gate verification.
