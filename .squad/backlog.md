# ADME Ingestion Tool — Backlog

Maintained by Satya. Last updated: 2026-05-15 (post manifest-generator ship + rebase onto merged PR #10).

This document is the source of truth for what we're working on, what's next, and what's been deferred. `decisions.md` records *why* we decided what; this doc records *what* and *when*. When priorities change, update here first.

## Definitions

- **Now**: actively being worked or next up — one or two items max.
- **Next**: confirmed, scheduled immediately after Now.
- **Later**: agreed-on direction, not scheduled yet.
- **Ideas**: needs discussion before commitment.
- **Tech debt / follow-ups**: small cleanups flagged by agents during shipping.
- **Done**: shipped, with rough date and headline.

Size scale: **XS** (≤1 hr touch-up) · **S** (single page/module, few hours) · **M** (new page or service, half/full day) · **L** (multi-page feature, multi-agent, 2+ days) · **XL** (architectural).

---

## Now

### 1. Run history page — **S/M** — owner: Judson
A cross-session list of past workflow runs (run id, kind, status, latency, when) so operators can see what they've ingested today without scrolling through `ingestion_history` in the current Streamlit session. Should also surface recent file uploads (record id, FileSource, size, when) now that File Upload v1 ships. Storage: simple JSON sidecar or SQLite — pick whatever Scott/Kevin think is least surprising. This unlocks "did I already ingest/upload this?" without re-hitting OSDU.

---

## Next

### 2. Wire "Generate from CSV" into Bulk Load page — **S/M** — owner: Judson + Kevin
The `manifest_generator.py` service is built and tested (list_schema_kinds, extract_schema_fields, auto_map, generate_manifests). Wire it into the Bulk Load page as a "Generate from CSV" flow: operator picks an OSDU kind → uploads a CSV → reviews the auto-mapped columns in an editable table → confirms → generates manifests → feeds into the existing submit pipeline. This completes the "any customer data" story.

### 2b. Generate TNO master-data manifests — **S** — owner: Kevin + Darryl
Run the manifest generator against the TNO sample CSVs (`app/data/datasets/tno/csv/`), produce loadable `load_*.json` files at `app/data/osdu/rc--3.0.0/master-data/`, flip `dataset.json` enabled flag. Zero code changes to bulk_loader needed — just data vendoring. Blocked only by confirming the sample CSVs cover the upstream entities adequately.

### 2c. AI-assisted schema mapping (v2 mapper) — **M** — owner: Kevin + Darryl review
When `auto_map()` returns low confidence (many unmatched required fields), offer an "🤖 AI Suggest" flow that sends OSDU schema fields + CSV headers + sample rows to an LLM and returns proposed `FieldMapping` pairs the operator can review/edit. Requires Azure OpenAI (or configurable model endpoint). Returns the same `MappingResult` shape as the heuristic so the UI doesn't change. Scope: `ai_map()` function in `manifest_generator.py`, config for model endpoint, and the "AI Suggest" button in the Bulk Load page CSV flow.

---

## Later

### 4. Bulk ingestion submit — **M** — owner: Judson + Kevin
Paste-many or queue several manifests at once with one progress view. Waits for run history (#2) so the result list has somewhere to live.

### 5. Saved searches — **S** — owner: Judson
Name + persist a `(kind, query, returnedFields, limit)` tuple locally so operators can re-run a frequent query without retyping. Pairs with run history's storage choice. Reference UX grounding: [OSDUBootcamp Module 4](https://github.com/EirikHaughom/OSDUBootcamp/tree/main/Labs/Module%204%20-%20Constructing%20Searches) — shows the building blocks operators compose (kind filter, Lucene query, field projection, limit). The save flow should capture all four.

### 6. Export search results — **S** — owner: Judson
"Download CSV / JSON" on the Search page so operators can hand a result set to a notebook or share with a colleague. For result sets > 1000, use the cursor search API (`/api/search/v2/query/cursor`) to paginate through all results before export. Honor the OSDU 10,000 totalCount ceiling and warn when the result set is bigger than what's been pulled. Reference: [OSDUBootcamp Module 4 §4.2](https://github.com/EirikHaughom/OSDUBootcamp/tree/main/Labs/Module%204%20-%20Constructing%20Searches) — cursor pagination pattern.

### 7. CSV → manifest helper — **M** — owner: Judson + Kevin — ✅ DONE (2026-05-13)
Shipped as `app/services/manifest_generator.py`: list_schema_kinds, load_schema, extract_schema_fields, auto_map (heuristic fuzzy matching), generate_manifests. 36 tests. Pure Python, no new deps. Page wiring is item #2 above.

### 8. Record edit / delete (Storage write paths) — **M** — owner: Kevin
Today Search can *view* a full record (GET `/api/storage/v2/records/{id}`). Adding edit (`PUT`) and delete (`DELETE`) lets the Search page round-trip changes. Security-sensitive — needs explicit confirmation UI and a clear "this writes to OSDU" affordance.

### 9. Multi-kind filter on Search — **S** — owner: Judson
Today the kind dropdown is single-select (or wildcard). OSDU Search accepts a `kind: []` array; surface that as a multiselect when an operator wants to scope across e.g. `Well` + `Wellbore`. Trivial backend change, modest UI change. Also add `aggregateBy: "kind"` support so operators can see record counts per kind before drilling in. Reference: [OSDUBootcamp §4.1.3 + §4.1.11](https://github.com/EirikHaughom/OSDUBootcamp/tree/main/Labs/Module%204%20-%20Constructing%20Searches).

### 10. Field-builder UI for Search queries — **M** — owner: Judson
Helper to compose Lucene queries field-by-field (pick a field, pick an operator, pick a value) instead of typing raw Lucene. Should support: `data.{field}:{value}` patterns, `.keyword` exact match, AND/OR combinators, `returnedFields` projection. Reference: [OSDUBootcamp §4.1.5–§4.1.10](https://github.com/EirikHaughom/OSDUBootcamp/tree/main/Labs/Module%204%20-%20Constructing%20Searches) — covers the full query grammar operators need.

### 11. App branding / favicon / About page — **XS** — owner: Scott or Judson
Replace the default Streamlit branding, add an About page with build/version info and a link to the GitHub repo. Cosmetic; do it once the feature surface stabilizes.

### 12. Operator quickstart doc — **S** — owner: Scott
Standalone `docs/quickstart.md` (or expanded README section) walking a new operator from clone → run → first ingest. README has prerequisites today; this is the missing "happy path" narrative.

---

## Ideas

These need conversation before they become commitments — flagging them so they don't get lost.

### 13. Geo-spatial / GIS search — **L** — owner: TBD
OSDU Search supports `spatialFilter` (bounding box, distance, polygon). Useful for E&P workflows but introduces a map widget (folium / pydeck) and a real UX question: what does the result look like, a list or a map? Defer until a user explicitly asks for it.

### 14. Open PR #11 against `EirikHaughom/adme-ingestion-tool` — owner: Satya + Brady
Brady's fork has shipped four big features (Entitlements, Legal Tags, Ingestion, Search) plus auth refactor that the upstream doesn't have. Worth a conversation about scope, commit history cleanup, and whether to PR each feature separately or as one squash. Not a coding task — a coordination decision.

### 15. Replace `verification.py` with `search.py` — **S** — owner: Kevin
Kevin flagged during Search v1 that `verification.py::search_records_by_kind` duplicates ~120 LOC of HTTP plumbing (`_call_search`, correlation extraction, JSON parsing, truncation) that now also lives in `search.py` and `legal_tags.py`. The post-ingest verification flow could call `search.search_records` directly and the orphan `SearchResult` dataclass could be deleted. See tech debt list — could also be a "Next" candidate if we do another ingestion-touching feature.

### 16. Extract shared HTTP plumbing into `app/services/_http.py` — **M** — owner: Kevin
The deeper version of #15: `_call_*` / correlation / JSON helpers are now triplicated across `legal_tags.py`, `verification.py`, `search.py`. One internal helper module would DRY the lot. Pure refactor — schedule when a service-touching feature is already in flight.

---

## Tech debt / follow-ups

Small flagged items from shipping. Not features; do opportunistically.

- **Reconcile legal-tag update body shape** (Kevin, from `kevin-legal-tags-impl-notes.md`) — flagged a 400-risk where PUT body shape may not match OSDU's expectation under some property combinations. Low-frequency, but worth verifying with a partition that has real tags.
- **Orphan `SearchResult` dataclass cleanup** (Kevin, search v1 follow-up) — kept because `verification.py` + page 4 still import it. Cleared with #15 above.
- **`sort` as kwarg on `search.search_records`** (Kevin) — today fixed to `createTime DESC`. Promote to kwarg if a future Search feature needs relevance ordering (omit `sort` → `_score DESC`).
- **`sample_limit` kwarg on `search.list_kinds`** (Kevin) — currently 100 for the page-sample fallback; lift if dropdowns look sparse in real partitions.
- **Page warning text** (Charlie, ingestion review) — Page 4 post-ingest warning reads "search index has not caught up yet" while the contract said "indexing delayed". Semantically equivalent; align if anyone is in the file.
- **README operator-flow wording drift check** (Scott, auth review) — already fixed once for MSAL; re-scan when a new auth-touching feature lands so we don't reintroduce stale "separate tab" wording.
- **Patch File Upload contract doc** (Satya, from `kevin-file-upload-impl.md`) — three divergences shipped against Darryl's authoritative cite: (a) `kind` uses literal `osdu:` schema authority, not `{partition}:` prefix; (b) `FILES_TIMEOUT_SECONDS = 15`, not 10; (c) metadata POST body includes `"status": "compliant"` in the `legal` block. Wire shape is correct as shipped; the contract doc just needs to catch up.
- **File Service uploadURL 5xx retry policy** (Kevin, file upload v1 open question) — `get_upload_url` currently does no internal retries on rare ADME 5xx, matching the established service pattern (page handles re-run UX). Confirm with Brady whether this stays or gets a bounded retry; if it changes, revisit the legal_tags / search / ingestion services for consistency.
- **Chunked upload for files > 100 MB** (Darryl, file upload research) — v1 caps single-PUT at 100 MB (`MAX_FILE_BYTES_V1`). Anything larger needs Azure Put Block + Put Block List with progress + resume; out of scope for v1 but worth a follow-up when an operator hits the cap. Page should show a clear "use Azure Storage Explorer + manual metadata POST" hint when the gate trips.

---

## Done

- **Manifest Builder v1 (Ingest › Manifest)** — 2026-05-11 — form-driven construction of a single `osdu:wks:dataset--File.Generic:1.0.0` manifest from operator inputs, exposed as a `🛠️ Build manifest` expander above the manifest editor on the Manifest page. Two pick modes: "From recent uploads" (reads in-session `upload_summary` rows produced by the File Upload page) and "Paste manually" (operator supplies FileSource + record id directly). Auto-fills display name, description, ACL/legal pickers; emits valid Workflow-ready JSON into the editor for review or hand-edit before submit. New pure service `app/services/manifest_builder.py` (`build_file_generic_manifest`), UI in `app/pages/5_📄_Manifest.py`. **Same shipping pass also reorganized the sidebar nav** into three groups — Setup / Ingest / Operate — and renamed/regrouped the File Upload and Manifest pages accordingly. **Validator loosened**: `Data` block on WPC records now accepts the OSDU work-product-component object shape (was previously over-strict). Walkthrough doc: `docs/walkthroughs/tno-end-to-end.md`. 713 tests pass.
File Upload page (Operate › File Upload)** — 2026-05-11 — branch `marielherz_FileUpload`, PR #12 (9 files, +3,251). Three-phase OSDU File Service v2 flow: GET `/api/file/v2/files/uploadURL` → PUT bytes to Azure signed URL (with `x-ms-blob-type: BlockBlob`) → POST `/api/file/v2/files/metadata`. New `app/services/files.py`, three result dataclasses (`UploadURLResult`, `UploadBytesResult`, `FileMetadataResult`), new page `6_📂_File_Upload.py`, 100 MB single-PUT cap. 600/600 tests pass.
- **
Shipping highlights. SHAs in git log; this is just the headline list.

- **Search page (Operate › Search)** — 2026-05-11 — kind dropdown + Lucene query + record fetch + pagination respecting OSDU 10,000 offset+limit ceiling. New `app/services/search.py`, four new dataclasses, +122 tests.
- **Ingestion MVP page (Operate › Ingestion)** — 2026-05-06 — manifest paste → legal-tag pre-flight → workflow submit → status polling → post-ingest verification. 152 tests, 88% coverage.
- **Legal Tags page (Setup › Legal Tags)** — full CRUD against `/api/legal/v1/legaltags`.
- **Entitlements page (Setup › Entitlements)** — group membership view for the authenticated principal.
- **Instance Configuration page** — connection form, keyring-backed secret storage, MSAL user-impersonation auth-code + PKCE flow with redirect-back-to-Streamlit, manual token-scope override.
- **MSAL auth refactor** — replaced `InteractiveBrowserCredential` with an app-managed MSAL `PublicClientApplication` flow on `http://localhost:8501`.
- **Squad team + governance scaffolding** — `.squad/` directory, charters, decision ledger, orchestration logs, casting registry.
