# Project Context

- **User:** Mariel (EMU-blocked Microsoft account)
- **Project:** ADME control plane Streamlit app — operator UI for
  Azure Data Manager for Energy.
- **Upstream:** `EirikHaughom/adme-ingestion-tool` (owner: Eirik
  Haughom). Mariel works via fork
  `marielherz/adme-ingestion-tool` and PRs upstream.
- **Branch:** `marielherz_Ingestion` (cut from
  `marielherz_Entitlements`).
- **In-flight upstream PRs:** #9 settings persistence + keyring,
  #10 entitlements page. Both will be rebased after Eirik merges.
- **Created:** 2026-05-06

## Stack

- Python 3.12 (x64 venv at `.venv/`)
- Streamlit 1.57
- `sqlite3` (stdlib) + `keyring` for settings persistence
- MSAL for interactive auth (InteractiveBrowserCredential), plus
  ClientSecretCredential for SP flows
- `requests` for OSDU/ADME HTTP calls
- `pytest` for tests, with a Streamlit recorder fixture under
  `tests/support/streamlit_recorder.py`

## Existing Code I Need To Know

- **Services (`app/services/`):**
  - `auth.py` — Kevin owns. `get_token(connection)`,
    InteractiveBrowserCredential + ClientSecretCredential paths,
    user-flow MSAL helpers, session-scoped user auth state.
  - `entitlements.py` — Kevin/Judson. `fetch_member_self`,
    `fetch_groups`, `EntitlementsCallResult`. Real path
    `/api/entitlements/v2/members/me`. This is the model I
    follow for new ingestion service modules: thin functions
    returning a dataclass, no Streamlit coupling.
  - `health.py` — Kevin. `check_all(connection, token)` against
    `OSDU_SERVICES`. Health = "is the service up". Distinct from
    "does my token work" (entitlements) and from "did my data
    actually land" (search-after-ingest, future).
  - `settings_store.py` — Kevin. sqlite at
    `~/.adme-ingestion-tool/settings.db` (override via
    `ADME_SETTINGS_DB`). `client_secret` is never persisted —
    keyring only.
  - `token_utils.py` — Kevin.

- **Pages (`app/pages/`):**
  - `app/main.py` — landing.
  - `1_⚙️_Settings.py` — connection config.
  - `2_🔑_Entitlements.py` — token-works smoke test.
  - **New ingestion page(s) go here.** Co-owned with Judson.

- **Models (`app/models/connection.py`):**
  - `ADMEConnection`, `ServiceHealthResult`,
    `EntitlementsCallResult`, `OSDU_SERVICES`. New ingestion
    dataclasses (e.g. `IngestionSubmissionResult`,
    `WorkflowRunStatus`) co-locate here unless they grow large.

## First Task

Study the OSDU TNO loader
(https://github.com/Azure/osdu-data-load-tno) and modern ADME
ingestion APIs. Propose an ingestion architecture for this app:
which endpoints, in what order, what each Streamlit page does, and
what "verify the record landed" looks like as a UX surface.

Deliverable: a decision note in
`.squad/decisions/inbox/darryl-ingestion-architecture.md` with the
proposed module layout under `app/services/`, the DAG(s) we will
trigger, the polling model, and the verify-step contract — each
endpoint flow emitted in the seven-field output discipline shape
from my charter.

## Learnings

(empty — first session)
