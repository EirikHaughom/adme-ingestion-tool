# ADME Ingestion Tool — Backlog

Maintained by Satya. Last updated: 2026-05-11.

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

### 1. File upload via OSDU File Service — **L** — owner: TBD (likely Kevin + Judson)
Signed-URL upload flow so operators can push a data file (LAS, CSV, segy, etc.) to ADME, get a file id back, and reference it from an ingestion manifest without leaving the app. This is the next big feature Brady has confirmed, and it unblocks "real" end-to-end ingestion (today the Ingestion page only accepts a manifest that already points at uploaded data).
- Needs: Darryl to write the File Service API brief (POST `/api/file/v2/files/uploadURL` → PUT to signed URL → finalize), Satya to lock the contract, Kevin to build `app/services/files.py`, Judson to add a "📤 Upload" page (or upload widget on Ingestion), Charlie to write tests.

---

## Next

### 2. Manifest builder UI — **M** — owner: Judson
Form-driven manifest construction for the common cases (single Master record, single Work-Product-Component, file reference) so an operator can ingest without hand-writing JSON. Pairs naturally with the file-upload work — the upload result auto-populates a file reference in the manifest. Out of scope: arbitrary schema-driven builder; we hand-pick 2–3 frequent kinds for v1.

### 3. Run history page — **S/M** — owner: Judson
A cross-session list of past workflow runs (run id, kind, status, latency, when) so operators can see what they've ingested today without scrolling through `ingestion_history` in the current Streamlit session. Storage: simple JSON sidecar or SQLite — pick whatever Scott/Kevin think is least surprising. This unlocks "did I already ingest this?" without re-hitting OSDU.

### 4. Switch ingestion legal-tag pre-flight to `POST /legaltags:validate` — **XS** — owner: Kevin (Darryl review)
Today the Ingestion page does `GET /legaltags/{name}` to confirm a tag exists before submitting a workflow. Darryl flagged that `POST /api/legal/v1/legaltags:validate` is the more correct call — it confirms the tag is *valid* (not just *present*) and returns the same shape the workflow service uses internally. Small, isolated change; do it before the next ingestion-touching feature ships.

---

## Later

### 5. Bulk ingestion submit — **M** — owner: Judson + Kevin
Paste-many or queue several manifests at once with one progress view. Waits for run history (#3) so the result list has somewhere to live.

### 6. Saved searches — **S** — owner: Judson
Name + persist a `(kind, query)` pair locally so operators can re-run a frequent query without retyping. Pairs with run history's storage choice.

### 7. Export search results — **S** — owner: Judson
"Download CSV / JSON" on the Search page so operators can hand a result set to a notebook or share with a colleague. Honor the OSDU 10,000 offset+limit ceiling and warn when the result set is bigger than what's been pulled.

### 8. CSV → manifest helper — **M** — owner: Judson + Kevin
Upload a CSV, map columns to a target kind's fields, emit a manifest. Brady has mentioned this twice; deferred until file upload + manifest builder are real.

### 9. Record edit / delete (Storage write paths) — **M** — owner: Kevin
Today Search can *view* a full record (GET `/api/storage/v2/records/{id}`). Adding edit (`PUT`) and delete (`DELETE`) lets the Search page round-trip changes. Security-sensitive — needs explicit confirmation UI and a clear "this writes to OSDU" affordance.

### 10. Multi-kind filter on Search — **S** — owner: Judson
Today the kind dropdown is single-select (or wildcard). OSDU Search accepts a `kind: []` array; surface that as a multiselect when an operator wants to scope across e.g. `Well` + `Wellbore`. Trivial backend change, modest UI change.

### 11. Field-builder UI for Search queries — **M** — owner: Judson
Helper to compose Lucene queries field-by-field (pick a field, pick an operator, pick a value) instead of typing raw Lucene. Out of v1 because Lucene works fine for now; this is operator-friendliness.

### 12. App branding / favicon / About page — **XS** — owner: Scott or Judson
Replace the default Streamlit branding, add an About page with build/version info and a link to the GitHub repo. Cosmetic; do it once the feature surface stabilizes.

### 13. Operator quickstart doc — **S** — owner: Scott
Standalone `docs/quickstart.md` (or expanded README section) walking a new operator from clone → run → first ingest. README has prerequisites today; this is the missing "happy path" narrative.

---

## Ideas

These need conversation before they become commitments — flagging them so they don't get lost.

### 14. Geo-spatial / GIS search — **L** — owner: TBD
OSDU Search supports `spatialFilter` (bounding box, distance, polygon). Useful for E&P workflows but introduces a map widget (folium / pydeck) and a real UX question: what does the result look like, a list or a map? Defer until a user explicitly asks for it.

### 15. Open PR #11 against `EirikHaughom/adme-ingestion-tool` — owner: Satya + Brady
Brady's fork has shipped four big features (Entitlements, Legal Tags, Ingestion, Search) plus auth refactor that the upstream doesn't have. Worth a conversation about scope, commit history cleanup, and whether to PR each feature separately or as one squash. Not a coding task — a coordination decision.

### 16. Replace `verification.py` with `search.py` — **S** — owner: Kevin
Kevin flagged during Search v1 that `verification.py::search_records_by_kind` duplicates ~120 LOC of HTTP plumbing (`_call_search`, correlation extraction, JSON parsing, truncation) that now also lives in `search.py` and `legal_tags.py`. The post-ingest verification flow could call `search.search_records` directly and the orphan `SearchResult` dataclass could be deleted. See tech debt list — could also be a "Next" candidate if we do another ingestion-touching feature.

### 17. Extract shared HTTP plumbing into `app/services/_http.py` — **M** — owner: Kevin
The deeper version of #16: `_call_*` / correlation / JSON helpers are now triplicated across `legal_tags.py`, `verification.py`, `search.py`. One internal helper module would DRY the lot. Pure refactor — schedule when a service-touching feature is already in flight.

---

## Tech debt / follow-ups

Small flagged items from shipping. Not features; do opportunistically.

- **Reconcile legal-tag update body shape** (Kevin, from `kevin-legal-tags-impl-notes.md`) — flagged a 400-risk where PUT body shape may not match OSDU's expectation under some property combinations. Low-frequency, but worth verifying with a partition that has real tags.
- **Orphan `SearchResult` dataclass cleanup** (Kevin, search v1 follow-up) — kept because `verification.py` + page 4 still import it. Cleared with #16 above.
- **`sort` as kwarg on `search.search_records`** (Kevin) — today fixed to `createTime DESC`. Promote to kwarg if a future Search feature needs relevance ordering (omit `sort` → `_score DESC`).
- **`sample_limit` kwarg on `search.list_kinds`** (Kevin) — currently 100 for the page-sample fallback; lift if dropdowns look sparse in real partitions.
- **Page warning text** (Charlie, ingestion review) — Page 4 post-ingest warning reads "search index has not caught up yet" while the contract said "indexing delayed". Semantically equivalent; align if anyone is in the file.
- **README operator-flow wording drift check** (Scott, auth review) — already fixed once for MSAL; re-scan when a new auth-touching feature lands so we don't reintroduce stale "separate tab" wording.

---

## Done

Shipping highlights. SHAs in git log; this is just the headline list.

- **Search page (Operate › Search)** — 2026-05-11 — kind dropdown + Lucene query + record fetch + pagination respecting OSDU 10,000 offset+limit ceiling. New `app/services/search.py`, four new dataclasses, +122 tests.
- **Ingestion MVP page (Operate › Ingestion)** — 2026-05-06 — manifest paste → legal-tag pre-flight → workflow submit → status polling → post-ingest verification. 152 tests, 88% coverage.
- **Legal Tags page (Setup › Legal Tags)** — full CRUD against `/api/legal/v1/legaltags`.
- **Entitlements page (Setup › Entitlements)** — group membership view for the authenticated principal.
- **Instance Configuration page** — connection form, keyring-backed secret storage, MSAL user-impersonation auth-code + PKCE flow with redirect-back-to-Streamlit, manual token-scope override.
- **MSAL auth refactor** — replaced `InteractiveBrowserCredential` with an app-managed MSAL `PublicClientApplication` flow on `http://localhost:8501`.
- **Squad team + governance scaffolding** — `.squad/` directory, charters, decision ledger, orchestration logs, casting registry.
