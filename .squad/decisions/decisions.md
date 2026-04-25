# Decisions

## Active Decisions

### 2026-04-24T14:20:35.493+02:00: Always use GitHub Issues for work tracking
**By:** Eirik Haughom (via Copilot)
**What:** Always use GitHub Issues for work tracking.
**Why:** User request — captured for team memory

### 2026-04-24T14:21:30.474+02:00: Always update GitHub issue with real status
**By:** Eirik Haughom (via Copilot)
**What:** Always update the relevant GitHub issue with the real status.
**Why:** User request — captured for team memory

### 2026-04-24T14:22:14.053+02:00: Streamlit environment architecture
**By:** Satya (Lead)
**What:** Established project structure using flat `app/` layout (not `src/`), `pyproject.toml` as single source of truth, and latest stable versions: Streamlit 1.56+, Python ≥3.11, ruff 0.15+, pytest 9.0+.
**Why:** Streamlit apps aren't libraries — flat layout keeps `streamlit run app/main.py` simple. Version floor of Python 3.11 balances modern features with broad compatibility. All tooling config lives in pyproject.toml to avoid config sprawl.

### Ownership split
- **Judson**: `app/main.py`, `app/pages/` — all Streamlit UI work
- **Kevin**: `app/services/` — ADME/OSDU API client backend
- **Scott**: `Dockerfile`, `.github/workflows/ci.yml`, Azure infra
- **Charlie**: `tests/` — test expansion, fixtures, CI integration

### 2026-04-24T14:38:18.059+02:00: ADME connection architecture (issue #2)
**By:** Satya (Lead)
**What:** Connection layer contract defined in `app/models/connection.py` (ADMEConnection, ServiceHealthResult dataclasses). Welcome page at `app/main.py`, settings page at `app/pages/1_⚙️_Settings.py`. Auth via azure-identity (DeviceCodeCredential for user impersonation, ClientSecretCredential for service principal). Health checks use concurrent OSDU API probes (5s timeout each, no dedicated /health endpoint). Session state for config, future .env/.secrets integration. data_partition_id required header.
**Why:** Operator-facing ADME control plane needs reliable connection setup with health validation before any workflows run. Concurrent probes prevent long blocking waits. Shared contract file ensures UI, services, and tests align. Changes to models require Satya sign-off.

#### Ownership (issue #2)
- **Kevin**: `app/services/auth.py`, `app/services/health.py` — service implementations
- **Judson**: `app/main.py` updates, `app/pages/1_⚙️_Settings.py` — UI pages
- **Charlie**: Tests for models, services, pages
- **Scott**: No work this sprint

#### Sequencing
1. Contract models (✓ committed: `app/models/connection.py`)
2. Parallel: Kevin builds services; Judson builds UI
3. After both land: Charlie writes integration tests

### 2026-04-24T14:38:18.059+02:00: ADME connection review gate (issue #2)
**By:** Charlie (Tester)
**What:** Issue #2 blocked on automated coverage for auth-mode-specific required fields, per-service health matrices for core M25 OSDU services (storage, search, schema, legal, entitlements, workflow, file, dataset, indexer, notification, eds), explicit partial-failure handling without secret leakage, and product signoff before any extra required inputs beyond contract.
**Why:** Happy-path-only demo not reviewable for operator tool. Critical review gates: auth switching, unauthorized services, timeouts, mixed health states. Must have test evidence for all dangerous paths before sign-off.

### 2026-04-24T14:38:18.059+02:00: Health probe status semantics (issue #2)
**By:** Kevin (Backend Dev)
**What:** Health probe results use explicit `healthy` / `unhealthy` / `error` semantics. `healthy` = probe reached service + 2xx response. `unhealthy` = probe reached service + non-2xx response (includes HTTP code and best-effort error detail). `error` = probe failed before response (timeout, DNS, TLS, connection failure; status_code=None). Probes do **not** follow redirects (redirects hide auth/gateway misconfig). `check_all()` returns results in OSDU_SERVICES order for deterministic UI/test rendering.
**Why:** Judson needs stable semantics for settings page rendering; Charlie needs same semantics for test assertions. Backend must surface gateway and auth failures distinctly, not smooth them over. Deterministic ordering allows matrix UI and tests to expect fixed service positions.

### 2026-04-24T14:38:18.059+02:00: Indexer probe uses readiness endpoint (issue #2)
**By:** Kevin (Backend Dev)
**What:** Indexer health probe changed from `GET /api/indexer/v2/reindex` (rejected by Charlie — mutating endpoint) to `GET /api/indexer/v2/readiness_check` (read-only, valid health check). Keep Indexer in service matrix; preserve health semantics in `app/services/health.py`. Updated tests to assert readiness endpoint.
**Why:** Charlie flagged reindex as non-idempotent health check. Readiness endpoint provides safe, non-mutating connectivity validation. Tests locked to readiness prevent accidental reversion to mutating path.

### 2026-04-24T14:38:18.059+02:00: EDS probe uses readiness endpoint (issue #2)
**By:** Kevin (Backend Dev)
**What:** EDS health probe set to `GET /api/eds/v1/health/readiness_check` (dedicated health endpoint). Do **not** use `POST /api/eds/v1/retrievalInstructions` for health checks — that endpoint requires business payload semantics and produces false negatives unrelated to service health. Keep EDS in issue #2 service matrix; return explicit health status per service.
**Why:** Charlie flagged EDS coverage in review gate. Search is the only POST probe (by design). EDS has dedicated health endpoints; using business APIs for health validation masks true service state and can block operator workflows on false negatives.

### 2026-04-24T14:38:18.059+02:00: Issue #2 final approval
**By:** Charlie (Tester)
**What:** Approve issue #2 after Kevin's revision. The Indexer probe contract now uses `GET /api/indexer/v2/readiness_check`, and the model plus health tests explicitly protect that fix from regressing back to `/reindex`. All review gates satisfied: contract inputs match implemented settings form, `client_secret` masked and session-scoped, UI renders service-by-service matrix, backend failures explicit, EDS and Indexer coverage present with passing validation.
**Why:** Re-review confirms Judson's welcome/settings pages, Kevin's auth/health services, and Charlie's test suite meet all acceptance criteria. Remaining non-blocking risk: live ADME/Entra validation before production use (operator responsibility).

### 2026-04-24T15:37:20.929+02:00: Streamlit import-path fix (issue #3)
**By:** Judson (Streamlit App Dev)
**What:** Fixed Streamlit multipage import-path failure by prepending repository root to `sys.path` at the top of `app/main.py` and `app/pages/1_⚙️_Settings.py`, before any local imports run. Kept existing `app/` package layout and absolute `app.*` imports. Added `tests/test_streamlit_import_paths.py` with subprocess-based regression tests that simulate Streamlit-style script loading for both entry point and page scripts.
**Why:** Streamlit executes multipage files from their script directory, which can omit repository root from Python's import search path. Absolute imports like `from app.models.connection import ADMEConnection` fail. Tiny bootstrap (`import sys; sys.path.insert(0, repo_root)`) is minimal, idempotent, and keeps current app structure intact. Regression tests prevent silent reversion.

### 2026-04-24T19:54:00.751+02:00: User directive — Use interactive login
**By:** Eirik Haughom (via Copilot)
**What:** Use interactive login for users instead of device-code sign-in when using user impersonation.
**Why:** User request — captured for team memory

### 2026-04-24T19:54:00.751+02:00: Interactive browser login design (issue #4)
**By:** Satya (Lead)
**What:** Replace `DeviceCodeCredential` with `InteractiveBrowserCredential` from `azure-identity` for `AuthMethod.USER_IMPERSONATION`. This is a direct 1:1 swap: same OAuth 2.0 authorization code grant, but opens system browser with standard Entra ID login page instead of device-code copy-paste flow. Affected files: `app/services/auth.py` (import, constructor, remove callback), `app/pages/1_⚙️_Settings.py` (update help text), `tests/test_auth.py` and `tests/test_auth_service.py` (monkeypatch targets and assertions). No changes to `app/models/connection.py`, `requirements.txt`, or service-principal auth.
**Why:** `DeviceCodeCredential` forces unnecessary friction for a desktop-launched Streamlit app. `InteractiveBrowserCredential` is the standard interactive flow for locally-run apps — better UX, same security model. No alternative Entra flow needed.

#### Implementation Notes
- `_build_credential()` calls `InteractiveBrowserCredential(client_id=..., tenant_id=...)` (no `prompt_callback`, no `redirect_uri` — defaults to localhost)
- Runtime caveats preserved: local-only assumption (fails on headless servers), existing `_close_credential()` pattern, existing `CredentialUnavailableError`/`ClientAuthenticationError`/`AzureError` exception chain, type annotations updated
- Design approved — ready for implementation

### 2026-04-24T19:54:00.751+02:00: Interactive login acceptance criteria & review gates (issue #4)
**By:** Charlie (Tester)
**What:** Defined acceptance criteria for interactive browser login change: (1) Auth behavior (credential instantiation, token acquisition, no callback, service principal unchanged, error handling without device-code language), (2) UI help text (browser sign-in guidance, remove device-code references, test connection flow, main page messaging), (3) Test coverage (unit tests for credential type and error messages, integration tests for browser workflow and cancellation, UI regression tests), (4) Reviewer gates (credential replacement, error handling/messages, UI/UX alignment, test coverage, headless fallback documentation).
**Why:** Happy-path-only change not reviewable without comprehensive gates. Must prove device code is gone, interactive credential active, service principal unchanged, UI text clean, retry guidance present, regression covered. Headless/non-interactive behavior must be explicit.

### 2026-04-24T19:54:00.751+02:00: Backend error handling for interactive login (issue #4)
**By:** Kevin (Backend Dev)
**What:** For `AuthMethod.USER_IMPERSONATION`, backend treats browser-based sign-in errors as interactive-login failures and tells operators to run **Test Connection** again if browser flow was blocked, closed, or unavailable. Keeps Satya's change surgical (direct `InteractiveBrowserCredential` swap). Headless/browser-blocked runs still fail gracefully through `CredentialUnavailableError`, but message explains browser expectation instead of device codes.
**Why:** Satisfies Charlie's gates by removing device-code language from backend failures while preserving service-principal behavior and error wording. Allows Judson to align UI copy to "browser sign-in" / "run Test Connection again" without backend conflicts.

### 2026-04-24T19:54:00.751+02:00: Interactive login UI decision (issue #4)
**By:** Judson (Streamlit App Dev)
**What:** Settings page now tells operators that **Test Connection** opens an interactive browser sign-in for user impersonation. After saving user-impersonation connection, follow-up guidance keeps operators on **Test Connection** for browser sign-in to run. Settings page failure states append **Run Test Connection again to retry** for consistent recovery. Backend auth and console/device-code behavior stay with Kevin's `app/services/auth.py` workstream.
**Why:** Clear, consistent operator guidance for new interactive browser login flow. Removes friction and aligns with modern OAuth expectations.

### 2026-04-25T19:44:06.175+02:00: Interactive auth callback fix design (issue #5)
**By:** Satya (Lead)
**What:** Interactive browser auth was failing post-callback with AADSTS7000218 / invalid_client because InteractiveBrowserCredential was using ADME confidential-client app ID instead of a public client. Fixed by using Azure CLI well-known public client ID ( 4b07795-a710-4f9e-9640-a91e60e60e08) for credential instantiation while preserving connection.client_id for ADME scope derivation ({client_id}/.default). No UI or model changes required. Optional future: add interactive_client_id field for custom public-client support.
**Why:** Browser sign-in succeeds but auth-code exchange fails because confidential clients require client_secret which InteractiveBrowserCredential doesn't send. Azure CLI's public client is trusted by all tenants and is the standard pattern for interactive auth flows accessing ADME. Token's audience remains the ADME resource via scope derivation.

### 2026-04-25T19:44:06.175+02:00: Interactive auth callback acceptance criteria & gates (issue #5)
**By:** Charlie (Tester)
**What:** Defined acceptance criteria and reviewer gates for successful end-to-end interactive auth after callback: (1) Browser sign-in completes and token exchange succeeds with no invalid_client error, (2) Settings page reports success with green validation summary, (3) No AADSTS7000218 errors, (4) Unit tests for callback success and error handling, (5) Integration tests for full settings flow, (6) Service principal auth regression coverage, (7) >=90% code coverage for auth module, (8) UX/messaging clarity.
**Why:** Interactive auth callback integration is complex; must prove browser-to-app exchange succeeds, session state transitions correctly, error handling covers invalid_client, and regression doesn't break service principal.

### 2026-04-25T19:44:06.175+02:00: Interactive auth callback implementation (issue #5)
**By:** Kevin (Backend Dev)
**What:** Updated pp/services/auth.py to use Azure CLI public client ID ( 4b07795-a710-4f9e-9640-a91e60e60e08) when creating InteractiveBrowserCredential for user impersonation. Preserved connection.client_id for ADME scope derivation. Preserved ClientSecretCredential for service principal unchanged. Updated 	ests/test_auth.py and 	ests/test_auth_service.py to assert public client ID and preserved ADME scope behavior. Added AADSTS7000218 regression test case. All validation clean: pytest, ruff, mypy passing; no regressions.
**Why:** Confidential clients reject public-client flows; Azure CLI's public client is trusted and standard pattern for interactive ADME access. No UI/model changes required — pure backend fix.

### 2026-04-25T19:54:06.175+02:00: Tenant-compatible interactive auth design (issue #6)
**By:** Satya (Lead)
**What:** Interactive browser auth was failing in IPS-Energy tenant with AADSTS700016 error on hardcoded Azure CLI public client ID (04b07795-a710-4f9e-9640-a91e60e60e08). Root cause: that app is blocked or not consented in customer's tenant. Solution: (1) Use customer's own configured client_id for InteractiveBrowserCredential instead of hardcoded public ID, (2) Hardcode ADME scope to https://energy.azure.com/.default (constant across all instances) instead of deriving from client_id. No UI or model changes required — customer already provides app registration in Settings form that is guaranteed to exist and be authorized in their tenant.
**Why:** Azure CLI public client is Microsoft's first-party app; some tenants block unregistered external applications via consent restrictions or conditional access. Customer's configured app registration is local to their tenant and already authorized by their admin. Scope is resource-based (ADME's energy.azure.com), not client-based, so must be constant for both interactive and service-principal flows.

#### Files to Change
- **Kevin (backend):** pp/services/auth.py (remove AZURE_CLI_PUBLIC_CLIENT_ID, use connection.client_id), pp/models/connection.py (hardcode scope property), tests (update assertions)
- **Judson (UI):** No changes required
- **Charlie (testing):** Update scope assertions in test_auth.py and test_auth_service.py

#### Implementation Notes
- InteractiveBrowserCredential instantiated with client_id=connection.client_id (user's app)
- Both auth methods (user impersonation and service principal) use scope https://energy.azure.com/.default
- Service-principal ClientSecretCredential logic unchanged, but now uses updated scope
- No new UI fields or user inputs required

### 2026-04-25T19:54:06.175+02:00: Tenant-compatible auth acceptance criteria & gates (issue #6)
**By:** Charlie (Tester)
**What:** Defined acceptance criteria for tenant-compatible auth fix: (1) Interactive browser login succeeds in IPS-Energy tenant with customer's own client ID (no AADSTS700016), (2) Scope is hardcoded to https://energy.azure.com/.default (not derived from client_id), (3) Service principal auth remains unchanged, (4) Unit tests updated for new scope and client ID behavior, (5) Integration tests confirm Settings flow succeeds, (6) Regression tests confirm service principal unchanged, (7) Documentation/code comments explain why hardcoded Azure CLI ID was removed.
**Why:** Tenant-specific auth failures require proof of fix in actual customer tenant. Scope hardcoding changes contract semantics; must verify both auth methods work with constant scope and customer's app registration. Regression testing ensures service principal and error handling still work.

### 2026-04-25T19:54:06.175+02:00: Tenant-compatible auth implementation (issue #6)
**By:** Kevin (Backend Dev)
**What:** Removed hardcoded AZURE_CLI_PUBLIC_CLIENT_ID; InteractiveBrowserCredential now uses connection.client_id (customer's own app registration). Updated ADMEConnection.scope property to return https://energy.azure.com/.default (hardcoded constant). Both interactive and service-principal auth now use this constant scope. Updated assertions in ests/test_auth.py and ests/test_auth_service.py to expect hardcoded scope and customer's client_id. All validation clean: pytest, ruff, mypy passing; no regressions.
**Why:** Customer's configured app is guaranteed to exist and be consented in their tenant. Hardcoded scope is resource-based (ADME's identity) and applies to all ADME instances uniformly. Removes tenant-specific auth failures and simplifies scope management.
