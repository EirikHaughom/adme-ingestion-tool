# NOTICE — vendored Azure TNO manifest scripts

## Source

- Repository: <https://github.com/Azure/osdu-data-load-tno>
- Commit SHA (HEAD of `main` when vendored): `0501bef19d71c8df465624181411ef2ab92db365`
- Commit date: 2025-08-04T12:05:14-04:00
- Vendored on: 2026-05-12 by Kevin (ADME Ingestion Tool team)

## License

Apache License 2.0. See the upstream repo's `LICENSE` file. Vendored files
retain their original Apache-2.0 license; this directory inherits those
terms regardless of the surrounding project's MIT license.

## Files vendored

From `src/generate-manifest-scripts/` in the upstream repo:

| File | Size | Purpose |
|---|---|---|
| `csv_to_json.py` | 29,898 bytes | Reads TNO CSV inputs and emits per-record OSDU JSON manifests. |
| `csv_to_json_wrapper.py` | 5,323 bytes | CLI wrapper around `csv_to_json.py` (handles `--schema-ns-name`, batching). |

`csv_to_json.py` is vendored **as-is** — no edits. An empty `__init__.py`
is added so Python can import the package. `csv_to_json_wrapper.py` keeps
the upstream behavior but has a local import shim so it works both as a
package module and as the original script.

## Why vendored (not pip-installed)

The upstream repo is not published to PyPI and has no stable release tag.
Vendoring at a pinned commit gives us a reproducible build without taking
a runtime dependency on a moving target.

## Refreshing

To pull a newer revision:

1. `git clone --depth 1 https://github.com/Azure/osdu-data-load-tno.git`
2. `git rev-parse HEAD` — record the new SHA
3. Copy `src/generate-manifest-scripts/csv_to_json.py` and `csv_to_json_wrapper.py`
   over the existing files
4. Re-apply the package/script import shim in `csv_to_json_wrapper.py`
5. Update the **Commit SHA** and **Commit date** lines above
6. Run the test in `tests/test_tno_vendor.py` and the existing pytest suite

## Lint / type-check exclusions

The vendored files are excluded from project lint and type-check rules in
`pyproject.toml` (`tool.ruff.extend-exclude`, `tool.mypy.overrides` for
`app.vendor.*`). Do not "fix" or reformat the upstream code — that defeats
the point of vendoring at a pinned commit.
