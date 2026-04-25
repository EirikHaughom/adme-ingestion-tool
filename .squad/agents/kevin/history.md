# Project Context

- **Owner:** Eirik Haughom
- **Project:** Streamlit control plane app for Azure Data Manager for Energy (ADME)
- **Stack:** Python, Streamlit, Azure, ADME/OSDU APIs
- **Created:** 2026-04-24

## Learnings

- Kevin owns backend services, ADME integrations, and data-handling logic for the control plane.
- Reliability and explicit error handling matter because the app coordinates platform operations, not just passive reporting.
- `app/models/connection.py` is the shared ADME contract; backend auth and health services should consume `ADMEConnection`, `ServiceHealthResult`, and `OSDU_SERVICES` without redefining them.
- Judson's backend-facing API for issue #2 is intentionally thin: `app/services/auth.py:get_token(connection)` and `app/services/health.py:check_all(connection, token)`.
- Health validation should preserve `OSDU_SERVICES` order, classify non-2xx HTTP responses as `unhealthy`, and classify transport failures like timeouts as `error`.
- Health probes must send both `Authorization` and `data-partition-id`, and tests should keep `tests/conftest.py` fixtures aligned with that required input.
- EDS belongs in the issue #2 service matrix and should use the explicit readiness health endpoint (`/api/eds/v1/health/readiness_check`) with `GET`, not the business `retrievalInstructions` API.
- Indexer health validation must use the non-mutating readiness endpoint (`/api/indexer/v2/readiness_check`); `reindex` is an operational action, not a safe probe contract.

## 2026-04-24 Issue #2 Contract Corrections (Revision Batch)
- Fixed Indexer probe contract: removed mutating GET /api/indexer/v2/reindex, replaced with read-only GET /api/indexer/v2/readiness_check
- Finalized EDS probe: confirmed GET /api/eds/v1/health/readiness_check (dedicated health endpoint), rejected POST /api/eds/v1/retrievalInstructions (business API, false negatives)
- Established health status semantics: healthy (2xx), unhealthy (non-2xx with code/detail), error (transport/timeout, no status_code)
- No redirect following (redirects hide auth/gateway misconfig)
- Deterministic result ordering per OSDU_SERVICES list for UI/test matrix rendering
- All tests updated and re-run against corrected contracts
- Issue #2 updated with real current status
- Ready for Judson's UI integration

## 2026-04-24 Issue #2 Implementation Complete
- Implemented app/services/auth.py: get_token(connection) function with DeviceCodeCredential (user impersonation) and ClientSecretCredential (service principal) flows
- Implemented app/services/health.py: check_all(connection, token) with concurrent ThreadPoolExecutor probes, 5s timeout per service, explicit healthy/unhealthy/error semantics
- Probes consume OSDU_SERVICES canonical list, return results in deterministic order (enables matrix UI and test assertions)
- Includes corrected Indexer probe (GET /api/indexer/v2/readiness_check) and EDS probe (GET /api/eds/v1/health/readiness_check)
- No redirect following (prevents hiding auth/gateway misconfig)
- Error handling preserves meaningful messages without leaking secrets
- Backend tests validate auth flows, health probes, timeouts, partial failures, deterministic ordering
- Tests locked to readiness endpoints prevent reversion to mutating paths
- All backend tests passing, integrated with Judson's UI pages

## 2026-04-24 Issue #4 Backend Implementation Complete
- Replaced DeviceCodeCredential with InteractiveBrowserCredential in app/services/auth.py
- _build_credential() now calls: InteractiveBrowserCredential(client_id=..., tenant_id=...)
- Removed _device_code_prompt_callback() function (no longer needed)
- Updated error messages to reference 'interactive login' or 'browser authentication' instead of device codes
- Updated type annotations: DeviceCodeCredential | ClientSecretCredential → InteractiveBrowserCredential | ClientSecretCredential
- Service-principal auth unchanged (continues using ClientSecretCredential)
- Credential cleanup pattern (_close_credential()) preserved
- Error handling strategy: CredentialUnavailableError, ClientAuthenticationError, AzureError all provide "Run Test Connection again" guidance
- Updated tests: test_auth.py and test_auth_service.py monkeypatch InteractiveBrowserCredential, removed callback assertions
- All validation clean: pytest, ruff, mypy passing; no regressions in service-principal tests

## 2026-04-25 Issue #5 Interactive Auth Callback Fix Implementation
- Root cause: InteractiveBrowserCredential was passing ADME confidential-client app ID; Azure AD rejected post-callback token exchange with AADSTS7000218 because confidential clients require client_secret which public-client flows don't send
- Fixed by: Using Azure CLI well-known public client ID (`04b07795-a710-4f9e-9640-a91e60e60e08`) for credential instantiation while preserving `connection.client_id` for scope derivation
- Why it works: Azure CLI's public client is trusted by all Azure AD tenants; token's audience determined by scope, not client ID
- Changes: Added AZURE_CLI_PUBLIC_CLIENT_ID constant, updated _build_credential() USER_IMPERSONATION path, left service-principal path unchanged
- Tests: Updated test_auth.py and test_auth_service.py assertions, added AADSTS7000218 regression test, added callback success integration test
- Validation: All tests passing (18/18), ruff clean, mypy strict passing, no regressions, code coverage 93% (exceeds >=90% gate)
- Status: Implementation complete, approved for merge

## 2026-04-25 Issue #6 Tenant-Compatible Interactive Auth Implementation
- Root cause: Azure CLI public client ID is blocked in some enterprise tenants (IPS-Energy) due to consent policies or allowlists
- Solution: Removed hardcoded AZURE_CLI_PUBLIC_CLIENT_ID; InteractiveBrowserCredential now uses `connection.client_id` (customer's own app registration)
- Scope fix: Updated `ADMEConnection.scope` property to return hardcoded `https://energy.azure.com/.default` (constant across all ADME instances)
- Why it works: Customer's configured app is guaranteed to exist in their tenant and be authorized; hardcoded scope is resource-based (ADME's identity), not client-based
- Changes made:
  - `app/services/auth.py`: Removed AZURE_CLI_PUBLIC_CLIENT_ID constant; InteractiveBrowserCredential instantiation now uses connection.client_id
  - `app/models/connection.py`: scope property now returns hardcoded constant instead of deriving from client_id
  - Tests: Updated scope assertions in test_auth.py and test_auth_service.py; added test_interactive_uses_connection_client_id; added test_scope_is_hardcoded_adme_resource
- Validation: All tests passing (24/24), ruff clean, mypy strict passing, no regressions
- Service principal: Unchanged logic, uses same hardcoded scope
- Status: Implementation complete, approved for merge

## 2026-04-25 Issue #7 Auth Redirect Implementation
- Root cause: InteractiveBrowserCredential starts ephemeral HTTP server on localhost:8400 to capture OAuth code. SDK must receive code on that server; cannot redirect to Streamlit (8501) without breaking token exchange.
- Solution: Pass explicit `redirect_uri="http://localhost:8400"` to InteractiveBrowserCredential in app/services/auth.py
- Why explicit parameter: Makes port deterministic (no SDK-version drift), self-documents intended behavior, ensures alignment with app registration
- Changes made:
  - Added INTERACTIVE_BROWSER_REDIRECT_URI constant in app/services/auth.py
  - Updated _build_credential() USER_IMPERSONATION path to pass explicit redirect_uri parameter
  - Left ClientSecretCredential (service principal) behavior unchanged
  - Updated test assertions in test_auth.py and test_auth_service.py to verify redirect_uri parameter
- Validation: All tests passing (26/26), ruff clean, mypy clean, no regressions in service-principal tests
- Status: Implementation complete, approved for merge

