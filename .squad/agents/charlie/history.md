# Project Context

- **Owner:** Eirik Haughom
- **Project:** Streamlit control plane app for Azure Data Manager for Energy (ADME)
- **Stack:** Python, Streamlit, Azure, ADME/OSDU APIs
- **Created:** 2026-04-24

## Learnings

- Charlie owns test strategy, acceptance criteria, and quality gates for the control plane.
- The highest-risk areas are likely auth, operator actions, backend integration failures, and regression coverage.
- 2026-04-24: Issue #2 health validation should cover the core ADME/OSDU M25 services: storage, search, schema, legal, entitlements, workflow, file, dataset, indexer, notification, and eds.
- 2026-04-24: A reusable Streamlit test pattern in this repo is to monkeypatch the module-level `st` import with `tests.support.streamlit_recorder.StreamlitRecorder` and assert recorded UI calls.
- 2026-04-24: Key test paths for the welcome/settings work are `app/main.py`, `app/pages/`, `tests/conftest.py`, and `tests/test_main.py`.
- 2026-04-24: `app/models/connection.py` is the shared UI/backend contract for auth methods and health probes; verify scope drift on contract changes.
- 2026-05-05: Issue #8 auth review added regression coverage that distinguishes stale MSAL pending flows from newly generated retry flows after missing-pending, auth-denial, state-mismatch, and token-exchange failures.
- 2026-05-05: Manual token scope review accepted Kevin/Judson blank-as-default fallback (superseding Satya's earlier blank-invalid stance) since tests, auth behavior, and operator guidance stayed internally consistent. Settings field guidance must itself say token scope is not a token or secret — README-only safety wording is insufficient.
- 2026-05-05: Production Settings copy must satisfy lint gates (Ruff E501) in addition to assertion gates; lockout-safe revisions still need to clear lint.

## Reviewer log (older issues — full detail in history-archive.md)

- **Issue #2** (M25 health probes) — initial REJECT (Indexer probe used `/reindex` which is PATCH/POST, not a valid GET probe); Kevin reassigned per lockout. APPROVE after Kevin changed probe to `GET /api/indexer/v2/readiness_check`, locked in by tests. 11 services covered, client_secret masked, partial-failure semantics defined.
- **Issue #3** (Streamlit import path) — APPROVE. 4-line idempotent bootstrap, subprocess regression test.
- **Issue #4** (DeviceCode → InteractiveBrowser) — APPROVE. 92% auth.py coverage, headless fallback via `CredentialUnavailableError`.
- **Issue #5** (Azure CLI public client ID for user impersonation) — APPROVE. 93% coverage, AADSTS7000218 eliminated, service-principal path unchanged.
- **Issue #6** (customer's app registration + hardcoded ADME scope) — APPROVE. 24/24 tests; AZURE_CLI_PUBLIC_CLIENT_ID removed; scope hardcoded to `https://energy.azure.com/.default`.
- **Issue #7** (`redirect_uri="http://localhost:8400"`) — APPROVE. 26/26 tests; tenant-agnostic redirect URI, new-browser-tab UX guidance.

## Issue #8 Auth Flow — Team Completion (2026-05-05)

**Status:** APPROVE. Full suite 70 passed, Ruff + mypy clean. MSAL `PublicClientApplication` auth-code + PKCE replaces `InteractiveBrowserCredential` for user impersonation; service-principal path unchanged.

## 2026-05-05: Manual Token Scope Configuration

**Status:** APPROVE (final). Pytest 80, Ruff, mypy all clean. `ADMEConnection.token_scope` added; `connection.scope` accessor trims and falls back to ADME default. Both auth paths consume `connection.scope`. Settings exposes non-secret Token scope field with explicit non-secret guidance.

## 2026-05-05 Settings Store Persistence Tests

- Added `tests/test_settings_store.py` (20 tests): round-trip save/load, `client_secret` drop asserted via loaded model AND raw on-disk bytes, single-active-row invariant via partial unique index, delete-of-active clears `get_active_connection_name()`, idempotent `initialize_store`, `ADME_SETTINGS_DB` env override, unknown/empty name handling, upsert preserves active flag.
- Extended `tests/test_connection_state.py` (+5): `ensure_session_defaults` hydrates `CONNECTION_KEY` from active stored row, returns None when nothing active, preserves in-flight session connection over disk value, swallows `SettingsStoreError` during hydration, `save_connection` writes through to store and marks active while dropping `client_secret`.
- Isolation: `monkeypatch.setenv("ADME_SETTINGS_DB", str(tmp_path / "settings.db"))`. No test touches `Path.home()`.
- Targeted suite: 35 passed in 2.02s. settings_store.py 84% coverage; connection_state.py 83%.
- Verdict: Kevin's implementation matches Satya's contract.

### 2026-05-05 — Test pollution from real ~/.adme-ingestion-tool/settings.db

**Symptom:** Two tests passed individually but failed in the full suite:
- `tests/test_main.py::test_main_prompts_operator_to_open_settings_when_not_configured`
- `tests/test_settings_page.py::test_settings_page_defaults_token_scope_to_adme_resource_scope`

**Root cause:** `app.connection_state.ensure_session_defaults` hydrates from the on-disk SQLite store via `settings_store.get_db_path()`. When a test did not set `ADME_SETTINGS_DB`, that resolved to `~/.adme-ingestion-tool/settings.db` — the operator's REAL profile DB, populated by actual app use. Hydration found an active stored connection and broke the "no configuration yet" assumption. Order-dependent because the operator's real DB was already populated before pytest started.

**Fix:** Autouse fixture `_isolate_settings_db` in `tests/conftest.py` that sets `ADME_SETTINGS_DB` to `tmp_path/settings.db` for EVERY test.

**Lesson — durable test isolation for environment-driven file paths:** If production code reads a path from the environment with a home-directory default, EVERY test must redirect that env var. Per-test opt-in fixtures are fragile — one new test that forgets to request the fixture re-opens the leak. Autouse is the only durable fix. Pattern: any module that reads `Path.home() / ...` or similar needs an autouse isolation fixture at the conftest root, not at individual test-file scope.

**No reset hook needed:** `app.services.settings_store` opens short-lived `sqlite3` connections via `closing()` per call with no module-level state. Switching the env var between tests is sufficient; no cache to clear.

### 2026-05-05 Entitlements service + page test pass — APPROVE with two non-blocking notes

**Files added:**
- `tests/test_entitlements_service.py` (24 tests): happy-path member.self + groups, 401/403/500 with JSON body, 502 with text body, missing correlation header, `Timeout` and `ConnectionError` transport failures, correlation-ID case-insensitive lookup across all four header names (parametrized) plus first-hit-wins and fallback-to-later-candidates, trailing-slash URL stripping, outgoing headers (Authorization Bearer, data-partition-id, Accept JSON, timeout=5, allow_redirects=False), invalid-connection ValueError, empty-token ValueError (parametrized).
- `tests/test_entitlements_page.py` (10 tests): no-connection preflight, user-impersonation no-token preflight, missing data partition preflight, auto-run-once on first render, no re-fire on second render without button, Re-run button bypasses guard, two history entries per run, clear-history button empties session state, error rendering surfaces friendly message + HTTP status + correlation_id, user-impersonation with stored `UserAuthState` runs the test.

**Recorder extension:** Added `StreamlitRecorder.expander` so `with st.expander(...)` blocks behave as context managers (Judson's page uses expanders for raw JSON; settings page never did, so this is a net-new tool).

**Test_main fix:** `test_main_prompts_operator_to_open_settings_when_not_configured` previously asserted exactly one `page_link` call; Judson's `main.py` deliberately adds a second `page_link` to the entitlements page. Updated the assertion to filter by args for the Settings link instead of unpacking the full list. The Entitlements link was an intentional UX addition, not a regression.

**Validation:**
- `python -m pytest -q tests/test_entitlements_service.py tests/test_entitlements_page.py`: 34 passed.
- `python -m pytest -q`: **139 passed**, 87% total coverage. `app/services/entitlements.py` 85%, `app/pages/2_🔑_Entitlements.py` 86%.
- `python -m ruff check` on touched test files: clean.

**Verdict: APPROVE.** Kevin's service and Judson's page satisfy Satya's contract for operators.

**Non-blocking flags (note, do not block):**
1. *URL discrepancy:* Satya's contract quoted `/api/entitlements/v2/members/{me}` with a literal `{me}` placeholder per the ADME doc convention. Kevin shipped `/me` (the actual ADME endpoint path operators must hit). The page test pins the URL operators see (`.../members/me`), which is correct. The contract text is the doc-ambiguity, not the implementation. Operators are unaffected.
2. *error_message convention:* Satya's contract said `error_message` defaults to empty string on success (mirroring `ServiceHealthResult`). The shipped `EntitlementsCallResult` defaults to `None` and Kevin sets it to `None` on success. The page reads `error_message` only on the failure path (`_render_error_block` with `or "Unknown error."`), so operators never see the difference. Note for future contract alignment but no operator-visible impact.

**Lessons:**
- *Streamlit page coverage requires the recorder to know every context manager the page uses.* Adding a new context-manager primitive to a page (`st.expander`) breaks every page test until the recorder gains a matching helper. Pattern: when a page introduces a new `with st.X(...)` block, add the matching `X` method to `StreamlitRecorder` returning `StreamlitContext` rather than relying on the `__getattr__` fallback (which returns `None`, not a context manager).
- *Cross-page assertion fragility:* `[item] = list_of_calls` style unpacking breaks the moment another agent adds a second of the same widget for unrelated UX. Prefer args-filtered selectors in shared/global page tests so navigation additions don't cause spurious failures.



### 2026-05-06 Entitlements 405 fix — APPROVE

**Files added/edited:**
- `tests/test_token_utils.py` (new, 17 tests): hand-crafted JWTs for `extract_object_id`. Happy path with `oid` claim, parametrized realistic UUIDs, padding edge cases (0/1/2 padding chars, byte-length asserted in-test), missing `oid`, empty token, single-segment, invalid base64, valid base64 + non-JSON payload, non-dict JSON payload, non-string `oid` (int/float/bool/None/list/dict — all collapse to `None` because the helper requires `isinstance(oid, str) and oid`), empty-string `oid`.
- `tests/test_entitlements_service.py` (rewrite, 27 tests): deleted all `fetch_member_self` tests; added `fetch_my_groups` mirror suite (happy path with ADME-shaped `{desId, memberEmail, groups}` payload, 401/403/500, timeout, `ConnectionError`, headers/timeout/allow_redirects, URL building with quoted OID + `?type=none`, special-char OID escapes `a+b/c d` to `a%2Bb%2Fc%20d`, trailing-slash endpoint stripping, empty-token + empty-OID + invalid-connection `ValueError`s); kept all `fetch_groups` tests + correlation-id case-insensitive parametrize.
- `tests/test_entitlements_page.py` (rewrite, 14 tests): deleted `fetch_member_self` tests; added no-OID preflight (HTTP not fired, `st.error` mentions Object ID, `page_link` to Settings), auto-run with `extract_object_id` called once and OID forwarded to `fetch_my_groups`, identity card renders `desId`/`memberEmail` from response, `Groups you belong to (N)` count header, empty-groups friendly admin info message, all-groups expander exists once + `expanded=False` + does NOT block `fetch_groups`, Re-run button bypasses guard, history has 2 entries with labels `members.{oid}.groups` and `groups`, error path surfaces message+status+correlation_id and suppresses the `Authenticated as` identity success.
- `tests/test_entitlements_page.py` reuses Judson's existing `StreamlitRecorder.expander`; no recorder extension needed.

**Validation:**
- Targeted: `python -m pytest -q tests/test_token_utils.py tests/test_entitlements_service.py tests/test_entitlements_page.py` -> **68 passed** in 10.38s.
- Full: `python -m pytest -q` -> **183 passed** in 10.37s, **87% total coverage**. `token_utils.py` 100%, `entitlements.py` 86%, `2_🔑_Entitlements.py` 90%.

**Verdict: APPROVE.** Kevin's URL is correct (`/api/entitlements/v2/members/{quoted_oid}/groups?type=none`, `urllib.parse.quote(safe="")`, Bearer + `data-partition-id` + JSON Accept, 5s timeout, no redirects, `ValueError` on empty OID). Judson's page hits every contract bullet: preflight OID guard with no HTTP fired, identity-from-my-groups, count header, friendly admin message on empty groups, secondary all-groups expander collapsed by default but not gating the call, Re-run bypass, 2-entry history with correct labels, error path with no identity card.

**Non-blocking note (do not block, log for future contract alignment):**
- Satya's contract specified `MY_GROUPS_ENDPOINT_LABEL = "members.{oid}.groups"` as a *constant* with literal `{oid}` placeholder, justified by "we want a stable history label that does **not** leak per-user OIDs into chart axes / session history." Kevin shipped a per-call interpolated label `f"members.{object_id}.groups"` with no constant exported. Judson's page mitigates the chart-axis leak with a regex collapse to `"my groups"`, but the history *table* still surfaces the raw OID. Operator-private data on operator-private machine, so impact is bounded — but flag for contract alignment if/when this label is consumed by a multi-tenant view.

**Lessons:**
- *JWT padding tests must assert their own preconditions.* Crafting a payload that exercises 1- or 2-char padding requires the JSON byte length to be `len % 3 == 2` or `== 1` respectively. Hand-counting fails silently if the payload happens to land on a 0-padding boundary; the test still passes but no longer covers the padding branch. Pattern: `assert len(json_bytes) % 3 == <expected>` inside the test, immediately before the encode call.
- *Reviewer rejection didn't fire here, but the `{oid}`-constant deviation is a textbook case where strict-vs-flexible interpretation of "label" matters.* When a contract specifies a constant *symbol* (not just a value), shipping an inline f-string is a contract breach even when the rendered string at runtime can be adapted to. Future Satya contracts that say "constant" should be treated as a structural test target (`from app.services.entitlements import MY_GROUPS_ENDPOINT_LABEL`).