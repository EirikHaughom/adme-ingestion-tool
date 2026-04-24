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
