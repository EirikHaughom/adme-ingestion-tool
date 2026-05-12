# OSDU open test data — `rc--3.0.0`

Vendored snapshot of the [OSDU Forum's open test data][src] used to seed an
ADME data partition with the OSDU reference data + schemas. Dataset-specific
bits (TNO, Volve, NOPIMS, …) live under [`app/data/datasets/`](../../datasets/);
this folder ships only the OSDU-generic pieces that every dataset reuses.

[src]: https://community.opengroup.org/osdu/data/open-test-data

> **Status:** v1 scope — **Reference Data only.** Master Data, Work Products,
> and file assets (logs, SEG-Y, …) are intentionally **not vendored** here.

## Where it came from

| Field | Value |
|---|---|
| Upstream repo | <https://community.opengroup.org/osdu/data/open-test-data> |
| Pinned at git tag | `v0.27.0` |
| Tag commit SHA | `39104c77005b163afe7eebfdc94d71f0efd8aaf0` |
| In-repo dataset folder | `rc--3.0.0/` |
| License | Apache-2.0 — see `NOTICE.md` |
| Vendored | 2026-05-12 |

`rc--3.0.0` is a **directory** in the upstream repo (NOT a git tag), used
to version the dataset itself. The closest matching git tag — `v0.27.0` —
is the actual revision we vendored from. See `NOTICE.md` for the full
explanation.

## What's here

```
reference-data/   13 OSDU manifest templates, ~40 KB total
schemas/         480 schema files, ~4.2 MB total
```

The 13 reference-data manifests cover OSDU type-system tables that every
data partition needs before any master-data / work-product load can
succeed:

| Manifest | What it loads |
|---|---|
| `load_refAliasNameType.OPEN.json` | AliasNameType (Borehole, BoreholeCode, …) |
| `load_refDrillingReasonType.OPEN.json` | DrillingReasonType vocabulary |
| `load_refFacilityEventType.OPEN.json` | FacilityEventType (drilled, abandoned, …) |
| `load_refFacilityStateType.OPEN.json` | FacilityStateType vocabulary |
| `load_refGeoPoliticalEntityType.OPEN.json` | GeoPoliticalEntityType (country, region, …) |
| `load_refMaterialType.OPEN.json` | MaterialType (cement, casing, …) |
| `load_refOperatingEnvironment.OPEN.json` | OperatingEnvironment (onshore, offshore, …) |
| `load_refSchemaFormatType.OPEN.json` | SchemaFormatType (CSV, LAS, …) |
| `load_refTrajectoryStationPropertyType.OPEN.json` | Trajectory station properties |
| `load_refUnitOfMeasure.OPEN.json` | UnitOfMeasure aliases |
| `load_refVerticalMeasurementPath.OPEN.json` | VerticalMeasurementPath vocabulary |
| `load_refVerticalMeasurementType.OPEN.json` | VerticalMeasurementType vocabulary |
| `load_refWellboreTrajectoryType.OPEN.json` | WellboreTrajectoryType vocabulary |

Each file is a top-level OSDU manifest of `"kind": "osdu:wks:Manifest:1.0.0"`
with a `"ReferenceData": [...]` array of records. They submit through the
same `/workflow/v1/workflow/...` runner that the Manifest page already
uses — no new ingestion plumbing required.

## What's missing (out of v1 scope)

- **Master Data** (Well, Wellbore, …) — future tier
- **Work Products / Work Product Components** — future tier
- **File assets** (well logs, SEG-Y, documents) — needs a separate
  acquisition story (Azure samples / object storage)
- **`1-data/`** CSV inputs and the master-data flow that consumes them
- The other dataset packs in the same repo (`NOPIMS/`, `Volve/`)

See backlog item #4 — *Full TNO dataset load* — for the long arc.

## Token shapes — what was found vs predicted

Darryl's vendor research predicted these would need pre-conversion:

- `<namespace>` → `{{DATA_PARTITION_ID}}` (recursive find/replace)
- Possibly `{{viewers}}`, `{{owners}}`, `{{legal-tag-name}}`

**Actual result of scanning all 493 vendored `.json` files: zero matches
for any of these tokens.** The reference-data manifests in `rc--3.0.0/`
do not use literal-text substitution tokens at all. They ship with:

- `"kind"` fields that hard-code the **literal** authority prefix
  `"osdu:wks:..."` — matches what the file-upload work also found.
- `"id"` fields that hard-code `"osdu:reference-data--..."` (literal
  `osdu:`, not a `<namespace>` token).
- **Empty arrays** for `acl.owners`, `acl.viewers`, and
  `legal.legaltags`. These need to be **filled at runtime by the loader**
  (programmatic, not text substitution) using values from connection
  state — the same way the Manifest page already populates these for
  hand-built manifests.

So the find/replace pass Darryl described is a **no-op** for what we
vendored. The token machinery (`substitute_manifest_placeholders`) is not
invoked on these files. The future loader will instead:

1. Parse each `.json` as a manifest object
2. Walk the `ReferenceData[*]` records
3. Populate `acl.{owners,viewers}` from the active connection's group DNs
4. Populate `legal.legaltags` from the user's selection
5. Submit through the existing `submit_manifest` path

The `csv_to_json_wrapper.py` script in `app/vendor/azure_tno_loader/`
**does** still reference `<namespace>` (as a CLI default), but that's
about CSV-driven master-data generation, not reference-data. We don't
touch that path in v1.

## Refreshing this snapshot

A future operator who wants to bump to a newer revision should:

1. `git clone https://community.opengroup.org/osdu/data/open-test-data.git`
2. `git tag -l 'v*'` — pick a newer tag
3. `git checkout <new-tag>`
4. List the dataset folders: there may be a newer `rc--4.x.x/` directory
   alongside `rc--3.0.0/`. Decide whether to upgrade the dataset version.
5. Copy `<new-tag>/rc--X.Y.Z/4-instances/TNO/reference-data/*` over
   `app/data/osdu/<old-version>/reference-data/`. Likewise for `3-schema/`
   if you also want fresh schemas.
6. Re-run the token-presence scan in `tests/test_tno_vendor.py` — if
   newer manifests *do* introduce `<namespace>` or `{{...}}` tokens, the
   test will fail and the loader implementation needs to grow a
   substitution pass.
7. Update `NOTICE.md`: new tag, new SHA, new date, new file inventory.
8. Update `pyproject.toml` if the directory path changes.

If this dance becomes routine, build a small `tools/vendor-tno.py` script
that automates steps 1–7. Out of scope for the initial vendor commit.

## Where the loader lives

**Nowhere yet.** This branch (`marielherz_TNOVendor`) ships **only** the
vendored data + scripts + this docs set. The actual loader service +
Streamlit page land in a later branch after the Run History service
(backlog #1) is available to record results.
