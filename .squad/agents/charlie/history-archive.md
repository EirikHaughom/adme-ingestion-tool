# Charlie History Archive (2026-04-24 to 2026-05-04)

This file contains archived history entries for Charlie (Tester) to keep history.md under 15KB. Entries are organized by issue and phase.

## 2026-04-24 Project Onboarding

- Charlie owns test strategy, acceptance criteria, and quality gates for the control plane.
- Highest-risk areas: auth, operator actions, backend integration failures, regression coverage.
- Core ADME/OSDU M25 services: storage, search, schema, legal, entitlements, workflow, file, dataset, indexer, notification, eds.
- Reusable Streamlit test pattern: monkeypatch module-level `st` import with `tests.support.streamlit_recorder.StreamlitRecorder`
- Key test paths: `app\main.py`, `app\pages\`, `tests\conftest.py`, `tests\test_main.py`
- Operator workflow needs: welcome/settings pages, two auth modes (user_impersonation, service_principal), required connection inputs, service-by-service health reporting

## Issue #2 ADME Connection Architecture (2026-04-24 to 2026-04-24)

**Testing Plan:**
- Coverage for auth-mode-specific required fields
- Per-service health matrices for M25 services
- Explicit partial-failure handling without secret leakage
- Product signoff before scope creep

**Phase 1 - Planning:**
- Identified critical review risks: auth switching, unauthorized access, timeouts, mixed health states
- Set review gate: blocked on test coverage for dangerous paths
- Identified scope drift concern on data_partition_id

**Phase 2 - Implementation Review:**
- Rejected because Indexer probe was `GET /api/indexer/v2/reindex` (mutating, invalid health check)
- Named Kevin as required reviser (Satya authored the contract, Kevin owns health probes)

**Phase 3 - Kevin's Fix:**
- Changed Indexer probe to `GET /api/indexer/v2/readiness_check` (read-only, valid)
- Tests updated to pin readiness endpoint and guard against regression
- Added EDS health endpoint coverage

**Final Approval (2026-04-24):**
- All acceptance criteria verified as met
- Auth-mode-specific field coverage (conditional client_secret)
- Per-service health matrices for all 11 M25 services
- Explicit partial-failure handling (no secret leakage)
- Indexer readiness probe regression protection
- No scope creep beyond contract
- Ready to close issue #2

## Issue #3 Streamlit Import-Path Fix (2026-04-24)

**Final Review & Approval:**
- Minimal impact (4-line bootstrap in app/main.py and page scripts)
- Idempotent (guards against double-insertion)
- Meaningful regression coverage (subprocess tests simulate Streamlit-style loading)
- No test regressions
- Production-ready
- Ready to close issue #3

## Issue #4 Interactive Browser Login (2026-04-24)

**Acceptance Criteria & Test Gates:**
- Auth behavior: DeviceCodeCredential removed, InteractiveBrowserCredential active
- UI help text: browser sign-in guidance present, device-code wording removed
- Test coverage: >=90% auth.py coverage, unit/integration tests passing
- Reviewer gates: credential replacement verified, error messages browser-friendly, service principal unchanged, headless fallback explicit

**Final Review & Approval (2026-04-24):**
- DeviceCodeCredential removed entirely (no imports, no references)
- InteractiveBrowserCredential active (correct import, instantiation, constructor call)
- Service-principal auth unchanged (ClientSecretCredential still used)
- UI text clean (browser guidance present, device-code wording removed)
- Error messages browser-friendly (browser login language, 'Run Test Connection again' guidance)
- Test coverage: 92% auth.py (exceeds 90% gate), all tests passing, no regressions
- Headless fallback: CredentialUnavailableError raised, graceful error handling
- Production-ready, ready to close issue #4

## Issue #5 Auth Callback Fix (2026-04-25)

**Acceptance Criteria & Test Gates:**
- Browser sign-in → token exchange success (no AADSTS7000218)
- Settings page success state
- Error handling (cancelled browser, unavailable)
- Code review: public client ID, scope preservation, service principal untouched
- Test coverage: >=90%, unit/integration/regression tests
- Integration: end-to-end Settings flow

**Final Review & Approval (2026-04-25):**
- Azure CLI public client ID correctly defined and used for USER_IMPERSONATION
- Service-principal ClientSecretCredential path unchanged
- Scope derivation uses connection.client_id (token audience = ADME resource)
- Test coverage: 93% (exceeds 90%)
- End-to-end Settings workflow: browser auth succeeds, green validation summary
- Error handling: AADSTS7000218 eliminated, CredentialUnavailableError graceful
- No blockers, production-ready, ready to close issue #5

## Issue #6 Tenant-Compatible Auth (2026-04-25)

**Testing Plan & Review Gates:**
- Multi-tenant auth preserved (tenant_id passed to InteractiveBrowserCredential)
- Token acquisition unchanged
- Session storage unaffected
- Unit tests verify credential construction with tenant_id
- Help text mentions tenant ID requirement

**Final Review & Approval (2026-04-25):**
- Tenant-aware auth behavior preserved
- Token acquisition and session storage unaffected
- Unit tests verify tenant_id passed to credential constructor
- Help text updated to mention tenant ID requirement
- No cross-tenant auth confusion
- Production-ready, ready to close issue #6

## Issue #7 Auth Redirect to Localhost (2026-04-25)

**Acceptance Criteria & Test Gates:**
- Interactive browser auth redirects to localhost:8400
- Settings page guidance matches implementation behavior
- No localhost:8400 in error messages (implementation detail)
- Tenant-aware auth preserved
- Token acquisition and session storage unchanged
- Unit tests verify redirect_uri parameter passed
- Help text audit and update required

**Final Review & Approval (2026-04-25):**
- InteractiveBrowserCredential receives explicit `redirect_uri="http://localhost:8400"`
- Settings page guidance matches implemented behavior
- Implementation detail (localhost:8400) not exposed in error messages
- Tenant-aware auth preserved
- Token acquisition and session storage unaffected
- Unit tests verify redirect_uri parameter passed to credential
- Help text consistent with behavior
- Multi-tenant compatibility verified
- Production-ready, ready to close issue #7

## Issue #8 MSAL Auth Integration (2026-05-05)

**Final Completion & Team Validation:**
- Satya: Lead review and final validation
- Kevin: Auth-service implementation (MSAL + pending flow handling)
- Scott: Documentation and README updates
- Judson: Settings page integration
- Charlie: Quality gate and regression coverage (distinguished stale vs new pending flows)
- Full test suite: 70 tests passing, Ruff clean, mypy clean
- Ready for merge

## Manual Token Scope Configuration (2026-05-05)

**Status:** COMPLETE
**Decision:** Manual token scope configuration merged to decisions.md
**Outcome:** ADMEConnection now includes token_scope field with ADME default fallback. Settings UI exposes non-secret Token scope field. Both auth paths consume connection.scope. Validation: pytest 80, ruff, mypy clean.

## Learnings Summary

- Reusable Streamlit test pattern (monkeypatch st) is effective for page-level testing
- Auth workflow testing requires coverage of mode switching, secret masking, and per-service health states
- Test gates must be comprehensive: credential behavior, error messages, UI text, regression coverage
- Multi-auth-mode design is complex; regression tests must distinguish stale flows from new ones
- Health probe selection is critical: avoid mutating endpoints, use read-only or dedicated health endpoints
- Operator UX requires clear messaging for browser redirects, tenant/scope requirements, and error recovery
- Team sign-off protocol: lead review, named reviser if issues found, comprehensive re-review after fixes
- Acceptance criteria defined upfront enable fast iteration and clear gate definition
