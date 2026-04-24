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
