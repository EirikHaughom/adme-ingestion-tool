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

### 2026-05-06: TNO reference sample manifest sourced for MVP ingestion page

- **Source:** https://github.com/Azure/osdu-data-load-tno/blob/v0.0.10/README.md,
  "Overview of Manifest Ingestion" → "Sample Manifest Ingestion Submission".
- **Why v0.0.10 and not main:** main branch is the C# rewrite that generates
  manifests programmatically from CSV templates; literal sample JSON only lives
  in the v0.0.10 (Python-era) README. Envelope shape is unchanged in modern ADME.
- **Chosen entity:** `osdu:wks:reference-data--AliasNameType:1.0.0`,
  id `{{DATA_PARTITION_ID}}:reference-data--AliasNameType:Borehole`.
  Reference data → no parent-record dependencies → safest possible smoke test.
- **Workflow endpoint:** `POST /api/workflow/v1/workflow/Osdu_ingest/workflowRun`.
  Body shape is `{ executionContext: { Payload: {...}, manifest: {...} } }`.
- **Service chain on success:** Workflow → Schema (validate) → Storage (write) →
  Indexer (background) → Search (verify by id query).
- **Size:** ~880 bytes raw / ~1.1 KB pretty / 33 lines. Fits a textarea easily.
- **Substitution tokens chosen for the MVP:** `{{DATA_PARTITION_ID}}`,
  `{{LEGAL_TAG_NAME}}`, `{{ACL_OWNERS}}`, `{{ACL_VIEWERS}}`. Partition comes from
  `ADMEConnection`; the other three are page text inputs.
- **Pre-flight requirements (operator must satisfy before Submit succeeds):**
  (a) legal tag exists in partition (Legal service GET),
  (b) both ACL groups exist (Entitlements service GET),
  (c) caller is a member of both groups (reuse Kevin's `fetch_member_self`).
  MVP pre-flights all three; v2 may auto-create.
- **Cross-references:** OSDU community Manifest Ingestion DAG project
  (https://community.opengroup.org/osdu/platform/data-flow/ingestion/ingestion-dags)
  confirms `Osdu_ingest` is the R3 DAG that consumes this envelope.
- **Decision doc:** `.squad/decisions/inbox/darryl-tno-sample-manifest.md`.

