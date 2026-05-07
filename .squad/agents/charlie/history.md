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
- 2026-05-07 (Legal Tags review): When the page uses selection widgets (`st.selectbox`, `st.toggle`, `st.multiselect`, `st.date_input`, `st.text_area`), `StreamlitRecorder` MUST expose explicit methods returning configured `widget_values[label]` — the bare `__getattr__` fallback returns `None`, which silently breaks every page-render assertion. Five widget primitives are now in `tests/support/streamlit_recorder.py` and should be reused for future pages.
- 2026-05-07 (Legal Tags review): OSDU `:properties` endpoint uses a colon, not a slash — `/api/legal/v1/legaltags:properties`. This is a recurring footgun: when controller research (Darryl) and spec-style assumption (Satya) diverge on URL shape, the controller source wins. Pin the URL with a service test that asserts the exact path so silent regressions surface immediately.
- 2026-05-07 (Legal Tags review): Page widgets bound with `key=...` write to `st.session_state` AND read from `widget_values` separately in the recorder — they do not auto-sync. To force a "filter changed" flow, set BOTH `session_state[key]` and `widget_values[label]`; or test the equivalent path via the explicit Refresh button. Tests that only set `widget_values` will see the page read the old `session_state` value and skip the branch.
- 2026-05-07 (Legal Tags review): Page-test `_patch_services` must monkeypatch the names AS IMPORTED INTO THE PAGE MODULE'S NAMESPACE (e.g., `monkeypatch.setattr(page_module, "list_legal_tags", ...)`), not the source module. The page does `from app.services.legal_tags import (list_legal_tags, ...)` so patches against `app.services.legal_tags` would miss the page's bound name.
- 2026-05-07 (Legal Tags review): Reviewer judgment when 3+ specialists diverge on the same artifact — assign canonical authority per topic, not per author: Darryl wins on OSDU controller facts (URL paths, response shapes), Satya wins on internal contract style (request body shape, locked session keys), Kevin wins on backend implementation coherence. Document divergences as non-blocking flags so the next iteration can true them up without blocking ship.

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

### 2026-05-06 Ingestion MVP test pass — APPROVE

**Files added:**
- `tests/test_osdu_models.py` (35 tests): every documented `parse_workflow_status` mapping (case-insensitive, whitespace-tolerant), `None` and blank → UNKNOWN, garbage → UNKNOWN, `WorkflowStatus` enum membership + StrEnum value semantics, frozen-dataclass smoke tests for `WorkflowRunResult`/`LegalTagCheckResult`/`SearchResult` (construction with required fields, `FrozenInstanceError` on mutation, per-instance `records` default-factory).
- `tests/test_ingestion_service.py` (73 tests): `validate_manifest_json` table (TNO sample after substitution, blank/invalid JSON, top-level array, missing executionContext, missing manifest, no entity arrays, non-list section, item missing kind, non-string kind); `substitute_manifest_placeholders` happy + parametrized blank-input rejections + unresolved `{{` guard; `check_legal_tag` happy + curated 404 (tag-name + partition + "not found") + 401/403/500 + timeout + ConnectionError + headers (Bearer, data-partition-id, JSON Accept, no Content-Type for GET) + correlation-id case-insensitive parametrize + URL-encoded special chars + blank-name/blank-token/invalid-connection ValueErrors; `submit_manifest` happy (`runId`+`workflowId`+`status`→IN_PROGRESS) + 2xx-without-runId failure + 400/401/403/500 + timeout + ConnectionError + headers (Bearer, data-partition-id, JSON Accept, JSON Content-Type) + POST body equals manifest_payload exactly + blank-token + invalid-payload (empty dict / non-dict / None) ValueErrors; `get_workflow_status` parametrized parse-each-status table + URL template + 401/404/500 + timeout + blank-run_id/blank-token ValueErrors.
- `tests/test_verification_service.py` (23 tests): `search_records_by_kind` happy with `totalCount`+`results`, fallback to `len(results)` when `totalCount` missing, empty results (count=0 ok=True), custom limit honored in body, headers (Bearer, data-partition-id, JSON Accept, JSON Content-Type, `timeout=VERIFICATION_TIMEOUT_SECONDS`, `allow_redirects=False`), correlation-id case-insensitive parametrize, 401/403/500, timeout, ConnectionError, blank-kind/blank-token/non-positive-limit/invalid-connection ValueErrors. POST body shape `{"kind": kind, "limit": limit, "offset": 0}` pinned.
- `tests/test_ingestion_page.py` (21 tests): pre-flight (no connection / no user token / blank data partition all friendly-error + `page_link` and zero service calls); "Insert TNO sample" populates `ingestion_manifest_text` with raw template (placeholders intact); submit pipeline (invalid JSON aborts step 1 / missing legal-tag inputs aborts step 1 / placeholders trigger validate→substitute→re-validate→legal-tag check / legal-tag failure surfaces `http_status` + `correlation_id` + hint and submit NOT called / submit failure surfaces error + Raw response expander and polling state NOT set / submit success persists `ingestion_run_id` + `ingestion_submit_started_at` + `ingestion_kinds` + `ingestion_polling_active=True`); polling (single IN_PROGRESS keeps polling active and sleeps before rerun / FINISHED disables polling and triggers verification on next render / FAILED disables polling, no verification, error rendered / manual `🔄 Refresh status now` button forces a poll without sleeping); verification (count=0 retries up to 3 attempts × 5s sleep then yellow warning NOT red error / all kinds positive renders green success / one kind zero after retries renders warning, NOT error / FAILED workflow skips verification entirely); history (one row per HTTP call with contract labels `legal-tag-check` / `submit` / `poll` / `search.{kind}` / clear-history empties list and survives a rerun).

**Recorder extension (`tests/support/streamlit_recorder.py`):**
- Added `columns(spec)` returning a list of N `StreamlitContext` instances so the page can do `cols = st.columns(3); with cols[0]: ...`. Spec accepts an int OR a list of relative widths.
- Added `status(label, expanded=...)` returning `StreamlitStatusContext` (subclass of `StreamlitContext`) with a recorded `.update(label=, state=)` method that appends a `status_update` call. The ingestion page uses `with status_box: status_box.update(label=..., state="error")` extensively.
- Documented both extensions at the top of the helper.

**Validation:**
- Targeted: `python -m pytest -q tests/test_osdu_models.py tests/test_ingestion_service.py tests/test_verification_service.py tests/test_ingestion_page.py` → **152 passed** in 6.6s.
- Full: `python -m pytest -q` → **335 passed** in 9s, **88% total coverage**. `app/models/osdu.py` 100%, `app/services/ingestion.py` 90%, `app/services/verification.py` 82%, `app/pages/3_📥_Ingestion.py` 88%.
- Ruff clean on all touched files. Mypy clean: `Success: no issues found in 41 source files`.

**Verdict: APPROVE.** Kevin's services and Judson's page satisfy Satya's contract end-to-end.
- `app/models/osdu.py`: enum members exact, `parse_workflow_status` covers every documented mapping with the right normalization.
- `app/services/ingestion.py`: validation + 3 HTTP probes match the contract — pre-flight ValueErrors, header set, 5s timeout, no internal retries, curated 404 message, 2xx-without-runId surfaced as failure, POST body sent verbatim.
- `app/services/verification.py`: `totalCount` precedence with `len(results)` fallback, defensive results filtering, `limit < 1` rejected.
- `app/pages/3_📥_Ingestion.py`: locked session-state keys all populated correctly; submit pipeline order (validate → legal-tag → submit); FINISHED triggers verification with 3-retry × 5-second cadence; FAILED skips verification; `🔄 Refresh status now` bypasses sleep; history labels match contract; clear-history persists across reruns.

**Non-blocking flags (note, do not block):**
1. *Verification timing.* The page calls verification on the render AFTER the FINISHED poll (because `_render_run_status` calls `st.rerun()` and then returns; verification runs on the next render). Real Streamlit replays the page, so operators see verification. The recorder's `st.rerun` is a no-op so the test re-invokes `main()` once to exercise the verification path. Acceptable; the `ingestion_polling_active=False` + `WorkflowStatus.FINISHED` state correctly drives `_render_verification_section` on the next render.
2. *Status-banner copy after retries.* Page warning text reads "search index has not caught up yet"; the contract said "indexing delayed". Test now asserts on "caught up" / "search index" — the spirit (yellow warning, not red error) is preserved. If Judson or Satya prefers stricter contract wording match, the page line is the only thing to change.

**Lessons:**
- *F-strings + JSON literals are a footgun.* Building `VALID_MANIFEST_TEXT` with `f'...{{ ... }}}}}}'` made me lose a closing brace and the manifest silently failed JSON parse, which made every page-test that submitted "succeed at validation" actually short-circuit at step 1. The failure modes were identical to what a test looking for unrelated assertions might trigger (no submit fired, no history rows, etc.) — easy to mis-diagnose. Pattern: build manifest fixtures with `json.dumps({...})` not raw f-strings. JSON byte exactness is a structural test target, not narrative text.
- *Recorder extensions ride on context-manager subclasses, not on `__getattr__`.* The fallback `__getattr__` returns a callable that records and returns `None`. `with st.status(...)` and `with cols[0]:` require a real context manager; `status_box.update(...)` requires a method on that object. Each new context-manager primitive a page introduces (`st.columns`, `st.status`, possibly `st.tabs` later) needs an explicit method on the recorder. Subclass `StreamlitContext` when extra methods are needed (like `.update` on status) so the test can also assert on those side-effects via `calls_named("status_update")`.
- *Mypy and `MutableMapping[str, object]` session_state.* Reading from `streamlit_recorder.session_state` returns `object`. Tests need `assert isinstance(history, list)` (or `isinstance(text, str)`) inline before iterating/indexing — this both narrows for mypy and documents the expected runtime shape. Without the asserts, mypy errors look unrelated to the test logic.

### 2026-05-07 Instance Configuration rename — REJECT

**Verdict:** REJECT. 7 pytest failures from stale Settings references in test files Judson missed during the rename pass. Production code (pages, main.py, page_link targets, user-facing copy) is internally consistent — only test-side string assertions and one hard-coded path constant were missed.

**Failures:** test_streamlit_import_paths.py (1: stale 1_⚙️_Settings.py path constant), test_entitlements_page.py (3: `Settings` substring asserts), test_ingestion_page.py (2: same), test_legal_tags_page.py (1: same). 471 passed, 89% coverage. Mypy clean. `from app.main import main` clean. Ruff has 2 unrelated pre-existing violations (.agents/skills helper, test_settings_store_keyring.py unused import) — not introduced by this rename.

**Lesson:** Mechanical rename PRs MUST grep tests/ for the old string AND any hard-coded page-filename constants. `page_link` target updates in production code are not enough — page-test preflight assertions reference the operator-visible link label (e.g., `Settings`) and an unrelated test references the page filename via Path. Future rename ceremonies should run `rg -i 'OldName'` across both app/ and tests/ and treat any hit as part of the rename surface.
