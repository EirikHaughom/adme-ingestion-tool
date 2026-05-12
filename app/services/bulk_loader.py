"""Bulk Load — dataset registry, preview, and sequential submit.

Filesystem-discovered datasets under ``app/data/datasets/*/dataset.json``.
No network in ``list_datasets``/``load_dataset``/``preview_tier`` — those
are pure file IO. ``submit_tier`` is a generator that delegates each
manifest to the existing :func:`app.services.ingestion.submit_manifest`
and yields one :class:`SubmitResult` per file.

Path safety: every resolved manifest path is asserted to live under
``app/data/`` so a malicious bring-your-own descriptor cannot
``../../../etc/passwd`` its way out.
"""

from __future__ import annotations

import copy
import json
import logging
from collections.abc import Callable, Iterator, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.models.connection import ADMEConnection
from app.models.osdu import (
    DatasetDescriptor,
    DatasetTier,
    ManifestPreview,
    SubmitResult,
)
from app.services.ingestion import submit_manifest

# TODO: remove ImportError guard once #13 (run_history) merges into main
# and add ``"bulk_load"`` to the allowed ``submit_source`` set in
# ``app/services/run_history.py``.
try:
    from app.services.run_history import (  # type: ignore[import-not-found]
        record_workflow_finish,
        record_workflow_submit,
    )
except ImportError:  # pragma: no cover - branch depends on merge order
    record_workflow_submit = None  # type: ignore[assignment]
    record_workflow_finish = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)

__all__ = [
    "DATASETS_ROOT",
    "DATA_ROOT",
    "SUBMIT_SOURCE",
    "list_datasets",
    "load_dataset",
    "preview_tier",
    "submit_tier",
]

SUBMIT_SOURCE = "bulk_load"

# ``app/data/`` is the security boundary: every resolved manifest path
# MUST live underneath it, no exceptions.
DATA_ROOT: Path = (Path(__file__).resolve().parent.parent / "data").resolve()
DATASETS_ROOT: Path = (DATA_ROOT / "datasets").resolve()

_TIER_TO_SECTION: dict[str, str] = {
    "reference-data": "ReferenceData",
    "master-data": "MasterData",
    "work-products": "Data",
}

_DATASET_CACHE: list[DatasetDescriptor] | None = None


def _clear_cache() -> None:
    """Drop the module-level dataset cache (tests + page mount)."""

    global _DATASET_CACHE
    _DATASET_CACHE = None


def _assert_under_data_root(path: Path) -> Path:
    """Return ``path.resolve()`` after asserting it lives under ``DATA_ROOT``.

    Raises ``ValueError`` if the resolved path is outside ``app/data/``.
    """
    resolved = path.resolve()
    try:
        resolved.relative_to(DATA_ROOT)
    except ValueError as exc:
        raise ValueError(
            f"Path {resolved!s} escapes the app/data/ sandbox."
        ) from exc
    return resolved


def _parse_tier(raw: Any) -> DatasetTier:
    if not isinstance(raw, dict):
        raise ValueError("tier entry must be a JSON object")
    # Default enabled to True when manifest_glob is present and no
    # explicit ``enabled`` key is given — matches the schema in
    # Satya's decision §2 where enabled tiers can omit the flag.
    manifest_glob = raw.get("manifest_glob")
    if "enabled" in raw:
        enabled = bool(raw["enabled"])
    else:
        enabled = manifest_glob is not None
    return DatasetTier(
        enabled=enabled,
        manifest_glob=(
            manifest_glob if isinstance(manifest_glob, str) else None
        ),
        description=(
            raw["description"]
            if isinstance(raw.get("description"), str)
            else None
        ),
        reason=raw["reason"] if isinstance(raw.get("reason"), str) else None,
    )


def _parse_descriptor(path: Path) -> DatasetDescriptor:
    """Parse a single ``dataset.json``. Raises ``ValueError`` on any error."""
    try:
        body = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"unreadable dataset.json: {exc}") from exc
    if not isinstance(body, dict):
        raise ValueError("dataset.json must be a JSON object")

    required = ("id", "display_name", "source_url", "notice_path")
    for key in required:
        if not isinstance(body.get(key), str) or not body[key]:
            raise ValueError(f"dataset.json missing string field {key!r}")

    tiers_raw = body.get("tiers")
    if not isinstance(tiers_raw, dict) or not tiers_raw:
        raise ValueError("dataset.json missing non-empty 'tiers' object")

    tiers: dict[str, DatasetTier] = {}
    for name, entry in tiers_raw.items():
        if not isinstance(name, str) or not name:
            raise ValueError("tier name must be a non-empty string")
        tiers[name] = _parse_tier(entry)

    return DatasetDescriptor(
        id=body["id"],
        display_name=body["display_name"],
        source_url=body["source_url"],
        notice_path=body["notice_path"],
        tiers=tiers,
        root_dir=path.parent.resolve(),
    )


def list_datasets() -> list[DatasetDescriptor]:
    """Scan ``app/data/datasets/*/dataset.json``; sorted by display_name.

    Malformed descriptors are logged and skipped, not raised. Result is
    cached at module level; call :func:`_clear_cache` to force a re-scan.
    """
    global _DATASET_CACHE
    if _DATASET_CACHE is not None:
        return list(_DATASET_CACHE)

    found: list[DatasetDescriptor] = []
    if DATASETS_ROOT.is_dir():
        for descriptor_path in sorted(DATASETS_ROOT.glob("*/dataset.json")):
            try:
                descriptor = _parse_descriptor(descriptor_path)
            except ValueError as exc:
                logger.warning(
                    "Skipping malformed dataset descriptor %s: %s",
                    descriptor_path,
                    exc,
                )
                continue
            found.append(descriptor)

    found.sort(key=lambda d: d.display_name.lower())
    _DATASET_CACHE = found
    return list(found)


def load_dataset(dataset_id: str) -> DatasetDescriptor:
    """Return the descriptor with this ``id``. Raises ``ValueError`` if absent."""
    for descriptor in list_datasets():
        if descriptor.id == dataset_id:
            return descriptor
    raise ValueError(f"Unknown dataset id: {dataset_id!r}")


def _resolve_tier(descriptor: DatasetDescriptor, tier: str) -> DatasetTier:
    tier_descriptor = descriptor.tiers.get(tier)
    if tier_descriptor is None:
        raise ValueError(
            f"Dataset {descriptor.id!r} has no tier {tier!r}."
        )
    if not tier_descriptor.enabled:
        reason = tier_descriptor.reason or "tier disabled"
        raise ValueError(
            f"Tier {tier!r} on dataset {descriptor.id!r} is disabled: "
            f"{reason}."
        )
    if not tier_descriptor.manifest_glob:
        raise ValueError(
            f"Tier {tier!r} on dataset {descriptor.id!r} is enabled but "
            f"has no manifest_glob."
        )
    return tier_descriptor


def _resolve_manifests(
    descriptor: DatasetDescriptor,
    tier_descriptor: DatasetTier,
) -> list[Path]:
    glob = tier_descriptor.manifest_glob
    assert glob is not None  # guarded by _resolve_tier
    base = descriptor.root_dir
    # Split the glob into a "static prefix" we can resolve safely and a
    # pattern we hand to glob.glob. We resolve the prefix first and
    # check it stays under DATA_ROOT, then expand.
    glob_path = (base / glob)
    # Resolve parent (with .. parts) then re-attach the wildcard segment.
    parent = glob_path.parent
    resolved_parent = _assert_under_data_root(parent)
    pattern = glob_path.name
    matches = sorted(resolved_parent.glob(pattern))
    safe_matches: list[Path] = []
    for match in matches:
        safe_matches.append(_assert_under_data_root(match))
    return safe_matches


def preview_tier(dataset_id: str, tier: str) -> list[ManifestPreview]:
    """Return one :class:`ManifestPreview` per manifest under this tier.

    Pure: no HTTP, no token. ``kind`` and ``record_count`` come from the
    manifest body itself. Raises ``ValueError`` if the dataset or tier
    is unknown, or if the tier is disabled.
    """
    descriptor = load_dataset(dataset_id)
    tier_descriptor = _resolve_tier(descriptor, tier)
    section = _TIER_TO_SECTION.get(tier, "ReferenceData")

    previews: list[ManifestPreview] = []
    for manifest_path in _resolve_manifests(descriptor, tier_descriptor):
        kind = ""
        record_count = 0
        try:
            body = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning(
                "Skipping unreadable manifest %s: %s", manifest_path, exc
            )
            continue
        if isinstance(body, dict):
            kind_raw = body.get("kind")
            kind = kind_raw if isinstance(kind_raw, str) else ""
            records = body.get(section)
            if isinstance(records, list):
                record_count = len(records)
        previews.append(
            ManifestPreview(
                path=manifest_path,
                filename=manifest_path.name,
                kind=kind,
                record_count=record_count,
                record_section=section,
            )
        )
    return previews


def _inject_acl_and_legal(
    manifest_body: dict[str, Any],
    *,
    section: str,
    acl_owners: Sequence[str],
    acl_viewers: Sequence[str],
    legal_tag: str,
) -> dict[str, Any]:
    """Return a deep copy of ``manifest_body`` with ACL/legal populated.

    Only empty arrays are overwritten — operator-provided values stay
    intact. We mutate the copy so the caller can keep the parsed body
    for diagnostics.
    """
    out = copy.deepcopy(manifest_body)
    records = out.get(section)
    if not isinstance(records, list):
        return out
    for record in records:
        if not isinstance(record, dict):
            continue
        acl = record.get("acl")
        if not isinstance(acl, dict):
            acl = {}
            record["acl"] = acl
        if not acl.get("owners"):
            acl["owners"] = list(acl_owners)
        if not acl.get("viewers"):
            acl["viewers"] = list(acl_viewers)
        legal = record.get("legal")
        if not isinstance(legal, dict):
            legal = {}
            record["legal"] = legal
        if not legal.get("legaltags"):
            legal["legaltags"] = [legal_tag]
    return out


def _extract_record_id(result: Any) -> str | None:
    raw = getattr(result, "raw_response", None)
    if isinstance(raw, dict):
        candidate = raw.get("recordId") or raw.get("record_id")
        if isinstance(candidate, str) and candidate:
            return candidate
    return None


def submit_tier(
    dataset_id: str,
    tier: str,
    *,
    acl_owners: Sequence[str],
    acl_viewers: Sequence[str],
    legal_tag: str,
    data_partition_id: str,
    connection: ADMEConnection,
    token: str,
    progress_callback: Callable[[SubmitResult], None] | None = None,
) -> Iterator[SubmitResult]:
    """Yield one :class:`SubmitResult` per manifest in this tier.

    Sequential — one submit at a time. A failure on one manifest yields
    an error result and the loop continues to the next file (v1 has no
    abort-on-error policy at the service layer; the page can stop
    consuming the iterator).
    """
    descriptor = load_dataset(dataset_id)
    tier_descriptor = _resolve_tier(descriptor, tier)
    section = _TIER_TO_SECTION.get(tier, "ReferenceData")
    manifests = _resolve_manifests(descriptor, tier_descriptor)

    for manifest_path in manifests:
        submitted_at = datetime.now(UTC)
        run_id: str | None = None
        record_id: str | None = None
        status = "error"
        error: str | None = None

        try:
            body = json.loads(manifest_path.read_text(encoding="utf-8"))
            if not isinstance(body, dict):
                raise ValueError("manifest body is not a JSON object")
            shaped = _inject_acl_and_legal(
                body,
                section=section,
                acl_owners=acl_owners,
                acl_viewers=acl_viewers,
                legal_tag=legal_tag,
            )
            payload = {
                "executionContext": {
                    "Payload": {
                        "AppKey": "adme-ingestion-tool",
                        "data-partition-id": data_partition_id,
                    },
                    "manifest": shaped,
                },
            }

            if record_workflow_submit is not None:
                try:
                    record_workflow_submit(
                        submit_source=SUBMIT_SOURCE,
                        dataset_id=dataset_id,
                        tier=tier,
                        manifest_path=str(manifest_path),
                    )
                except Exception:  # pragma: no cover - telemetry never fatal
                    logger.exception(
                        "record_workflow_submit failed for %s",
                        manifest_path,
                    )

            workflow_result = submit_manifest(connection, token, payload)
            if getattr(workflow_result, "ok", False):
                status = "success"
                run_id = getattr(workflow_result, "run_id", None)
                record_id = _extract_record_id(workflow_result)
            else:
                error = (
                    getattr(workflow_result, "error_message", None)
                    or "submit_manifest returned ok=False"
                )

            if record_workflow_finish is not None:
                try:
                    record_workflow_finish(
                        submit_source=SUBMIT_SOURCE,
                        dataset_id=dataset_id,
                        tier=tier,
                        manifest_path=str(manifest_path),
                        run_id=run_id,
                        status=status,
                        error=error,
                    )
                except Exception:  # pragma: no cover - telemetry never fatal
                    logger.exception(
                        "record_workflow_finish failed for %s",
                        manifest_path,
                    )
        except (OSError, json.JSONDecodeError, ValueError) as exc:
            error = str(exc) or exc.__class__.__name__
            logger.warning(
                "Manifest %s failed to submit: %s", manifest_path, exc
            )

        result = SubmitResult(
            manifest_path=manifest_path,
            filename=manifest_path.name,
            status=status,
            run_id=run_id,
            record_id=record_id,
            error=error,
            submitted_at=submitted_at,
        )
        if progress_callback is not None:
            try:
                progress_callback(result)
            except Exception:  # pragma: no cover - UI callback never fatal
                logger.exception("bulk_loader progress_callback failed")
        yield result
