# Project Context

- **Owner:** Eirik Haughom
- **Project:** Streamlit control plane app for Azure Data Manager for Energy (ADME)
- **Stack:** Python, Streamlit, Azure, ADME/OSDU APIs
- **Created:** 2026-04-24

## Learnings

- Satya owns scope, architecture decisions, and reviewer gating for the ADME control plane.
- The product is an operator-facing Streamlit app for managing ADME workflows and platform operations.
- 2026-04-24: Established project scaffolding — flat `app/` layout, `pyproject.toml` as config hub, latest stable deps (Streamlit 1.56+, Python ≥3.11, ruff 0.15+, pytest 9.0+).
- Key file paths: `app/main.py` (entry point), `pyproject.toml` (deps + tool config), `.streamlit/config.toml` (UI theme), `tests/` (test suite).
- Ownership: Judson=UI, Kevin=backend services, Scott=infra/CI, Charlie=tests.
- Design choice: flat `app/` over `src/` layout because Streamlit apps run with `streamlit run app/main.py`, not as installed packages.
- Streamlit theme uses Microsoft Fluent colors (#0078d4 primary) to match ADME branding.

## 2026-04-24 Scribe Consolidation
- Decision to use GitHub Issues for all work tracking (user directive)
- Decision to always update GitHub issues with real status (user directive)
- Streamlit architecture decision documented and archived
- Team ownership split documented: Judson=UI, Kevin=backend, Scott=infra, Charlie=tests

## 2026-04-24 ADME Connection Architecture (Issue #2)
- Defined shared contract in `app/models/connection.py`: `ADMEConnection`, `ServiceHealthResult`, `OSDU_SERVICES`.
- `ADMEConnection.is_valid()` enforces that SP auth requires client_secret.
- `data_partition_id` is a required input (OSDU APIs need the `data-partition-id` header).
- Auth approach: `DeviceCodeCredential` for user impersonation, `ClientSecretCredential` for SP — both via `azure-identity`.
- Health checks: No `/health` endpoint on OSDU services. Use cheap read-only API probes with 5 s timeout, run concurrently via `ThreadPoolExecutor`.
- Page structure: `app/main.py` = welcome, `app/pages/1_⚙️_Settings.py` = settings/connection.
- Backend services go in `app/services/auth.py` and `app/services/health.py`.
- Contract file (`app/models/connection.py`) is the shared interface — changes require lead sign-off.
- Kevin and Judson can work in parallel after the contract is committed.

## 2026-04-24 Issue #2 ADME Connection Design (Issue #2 Complete)
- Approved welcome and settings page architecture for connection management
- Committed shared contract in app/models/connection.py (ADMEConnection, ServiceHealthResult)
- Defined OSDU_SERVICES list for canonical health probes
- Auth design: azure-identity with DeviceCodeCredential (user) and ClientSecretCredential (SP)
- Health checks via concurrent OSDU API probes (5s timeout, no dedicated /health)
- UI: app/main.py (welcome), app/pages/1_⚙️_Settings.py (settings)
- Ownership split: Kevin=services, Judson=UI, Charlie=tests, Scott=no sprint work
- data_partition_id is required input (OSDU header requirement)
- Session state for config, future .env/.secrets support
- Contract file requires Satya sign-off for any changes
- Ready for parallel Kevin/Judson work; Charlie blocks on test coverage

## 2026-04-24 Issue #4 Interactive Browser Login Design
- Approved InteractiveBrowserCredential as correct replacement for DeviceCodeCredential
- Direct 1:1 swap: same OAuth 2.0 authorization code grant, better UX (browser opens automatically vs device-code copy-paste)
- Identified minimal affected files: app/services/auth.py, app/pages/1_⚙️_Settings.py, tests/test_auth.py, tests/test_auth_service.py
- No changes needed: app/models/connection.py, requirements.txt, pyproject.toml, service-principal auth
- Implementation notes documented: _build_credential() pattern, runtime caveats (local-only, credential cleanup, error handling, type annotations)
- Design approved — ready for implementation
