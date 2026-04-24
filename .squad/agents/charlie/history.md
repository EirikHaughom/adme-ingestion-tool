# Project Context

- **Owner:** Eirik Haughom
- **Project:** Streamlit control plane app for Azure Data Manager for Energy (ADME)
- **Stack:** Python, Streamlit, Azure, ADME/OSDU APIs
- **Created:** 2026-04-24

## Learnings

- Charlie owns test strategy, acceptance criteria, and quality gates for the control plane.
- The highest-risk areas are likely auth, operator actions, backend integration failures, and regression coverage.
- 2026-04-24T14:38:18.059+02:00: Issue #2 health validation should cover the core ADME/OSDU M25 services: storage, search, schema, legal, entitlements, workflow, file, dataset, indexer, notification, and eds.
- 2026-04-24T14:38:18.059+02:00: A reusable Streamlit test pattern in this repo is to monkeypatch the module-level `st` import with `tests.support.streamlit_recorder.StreamlitRecorder` and assert recorded UI calls.
- 2026-04-24T14:38:18.059+02:00: Key test paths for the welcome/settings work are `app\main.py`, `app\pages\`, `tests\conftest.py`, and `tests\test_main.py`.
- 2026-04-24T14:38:18.059+02:00: The requested operator workflow needs welcome/settings pages, two auth modes (`user_impersonation` and `service_principal`), required connection inputs, and service-by-service health reporting.
- 2026-04-24T14:38:18.059+02:00: `app\models\connection.py` is becoming the shared UI/backend contract for auth methods and health probes, but it currently introduces `data_partition_id` and omits `eds`, so review for issue #2 must check scope drift before approval.

## 2026-04-24 Issue #2 Test Strategy & Review Gate (Issue #2)
- Added acceptance criteria to issue #2: auth-mode coverage, per-service health matrices (M25: storage, search, schema, legal, entitlements, workflow, file, dataset, indexer, notification, eds)
- Created reusable Streamlit page-test scaffolding (monkeypatch st import with StreamlitRecorder)
- Developed auth-validation tests for mode switching and credential handling
- Identified critical review risks: auth switching, unauthorized access, timeouts, mixed health states
- Set review gate: blocked on test coverage for dangerous paths before product sign-off
- Key paths: app/main.py, app/pages/, tests/conftest.py, tests/test_main.py
- Coordinating with Satya on scope drift checks (data_partition_id, eds service inclusion)
