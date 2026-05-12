# TNO dataset — dataset-specific artifacts

This folder is reserved for **TNO-specific** data that is NOT part of the
generic OSDU open-test-data reference set:

- Master Data (Wellbore, Well, Field, Organisation, …)
- Work Products + Work Product Components (well logs, trajectories, …)
- File assets (LAS, SEG-Y, …) — typically referenced, not committed

The generic OSDU pieces (reference-data lookup tables, schemas) that the
TNO loader happens to vendor are shared with all OSDU datasets and live
under [`app/data/osdu/rc--3.0.0/`](../../osdu/rc--3.0.0/).

When a new dataset is added (e.g. Volve), it gets its own sibling folder
here — `app/data/datasets/volve/` — and reuses the same `app/data/osdu/`
schemas + reference-data.

## Status

The v1 Bulk Load page only writes reference-data and does not need
anything from this folder yet. The `dataset.json` in this folder
registers TNO with the Bulk Load registry; its `reference-data` tier
points at the shared `app/data/osdu/rc--3.0.0/reference-data/` glob,
and `master-data` + `work-products` are disabled with `reason="v2 — not
yet vendored"`.
