# NOTICE — vendored OSDU open test data (rc--3.0.0)

## Source

- Repository: <https://community.opengroup.org/osdu/data/open-test-data>
- Git tag (used to pin the working tree): **`v0.27.0`**
- Tag commit SHA: `39104c77005b163afe7eebfdc94d71f0efd8aaf0`
- In-repo dataset version directory: **`rc--3.0.0/`** (this is a top-level
  folder inside the repo, NOT a git tag — see note below)
- Vendored on: 2026-05-12 by Kevin (ADME Ingestion Tool team)

> **Why two version-looking strings?** The upstream repo carries multiple
> dataset revisions side-by-side as top-level folders (`rc--1.0.0/`,
> `rc--2.0.0/`, `rc--3.0.0/`). The project's git tags (`v0.27.0`, …) ship
> a snapshot of all of them together. We pin to `v0.27.0` (the newest tag
> that contains a `rc--3.0.0/` folder) and vendor only the contents of
> `rc--3.0.0/`. Darryl's research note used `rc--3.0.0` as a "tag-like"
> identifier; the actual git tag we used is `v0.27.0`. Both names appear
> in this NOTICE so a future operator can match either.

## License

Apache License 2.0. Verified in the upstream repo's `LICENSE` file
(`Apache License Version 2.0, January 2004 / http://www.apache.org/licenses/`).

## Files vendored

```
app/data/osdu/rc--3.0.0/
├── reference-data/   13 JSON manifest templates, ~40 KB total
│                     (from rc--3.0.0/4-instances/TNO/reference-data/ in upstream;
│                      contents are OSDU-generic lookup tables shared across datasets)
└── schemas/         474 JSON schema files, ~4.2 MB total
                     (from rc--3.0.0/3-schema/)
```

### `reference-data/` contents (verbatim copies of upstream filenames)

- `load_refAliasNameType.OPEN.json`
- `load_refDrillingReasonType.OPEN.json`
- `load_refFacilityEventType.OPEN.json`
- `load_refFacilityStateType.OPEN.json`
- `load_refGeoPoliticalEntityType.OPEN.json`
- `load_refMaterialType.OPEN.json`
- `load_refOperatingEnvironment.OPEN.json`
- `load_refSchemaFormatType.OPEN.json`
- `load_refTrajectoryStationPropertyType.OPEN.json`
- `load_refUnitOfMeasure.OPEN.json`
- `load_refVerticalMeasurementPath.OPEN.json`
- `load_refVerticalMeasurementType.OPEN.json`
- `load_refWellboreTrajectoryType.OPEN.json`

### `schemas/` contents

Mirror of `rc--3.0.0/3-schema/` top-level subdirectories:
`abstract/`, `data-collection/`, `dataset/`, `manifest/`, `master-data/`,
`reference-data/`, `type/`, `work-product/`, `work-product-component/`.

## What is **NOT** vendored (out of v1 scope)

- `1-data/` — bulk reference data, file assets (~hundreds of MB)
- `2-scripts/` — alternate loader scripts (we use Azure's instead)
- `4-instances/TNO/master-data/` — well/wellbore/wp manifests
- `4-instances/TNO/work-products/` — work-product manifests
- `4-instances/NOPIMS/`, `4-instances/Volve/` — other dataset packs
- `5-templates/`, `6-data-load-scripts/`

These are deferred to future v1+ tiers as backlog #4 expands.

## Refreshing

To pull a newer dataset revision, see `README.md` in this directory.
