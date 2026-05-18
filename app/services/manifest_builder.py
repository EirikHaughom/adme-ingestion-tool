"""Manifest Builder v1 — pure construction of File.Generic manifests.

Turns operator inputs (FileSource token + display metadata + ACL/legal)
into a workflow-ready manifest dict containing a single
``osdu:wks:dataset--File.Generic:1.0.0`` record. The output is suitable
for direct submission via :func:`app.services.ingestion.submit_manifest`.

Field shape mirrors the body constructed by
:func:`app.services.files.post_file_metadata` exactly (same ``acl``
block, same ``legal`` block including ``"status": "compliant"``, same
``data.DatasetProperties.FileSourceInfo`` layout), then wraps the
record in the OSDU Workflow Service ``executionContext`` envelope.

Pure: no HTTP, no IO, no Streamlit. Easy to test exhaustively.

Contract: ``.squad/decisions/inbox/satya-manifest-builder-contract.md``.
"""

from __future__ import annotations

from typing import Any

MANIFEST_WRAPPER_KIND = "osdu:wks:Manifest:1.0.0"
DEFAULT_DATASET_KIND = "osdu:wks:dataset--File.Generic:1.0.0"

__all__ = [
    "DEFAULT_DATASET_KIND",
    "MANIFEST_WRAPPER_KIND",
    "build_file_generic_manifest",
]


def build_file_generic_manifest(
    *,
    file_source: str,
    file_id: str,
    display_name: str,
    description: str,
    kind: str,
    legal_tag: str,
    acl_owners: str,
    acl_viewers: str,
    data_partition_id: str,
) -> dict:
    """Build a workflow-ready manifest containing one File.Generic dataset record.

    The returned dict is suitable for direct submission to the Workflow
    Service via :func:`app.services.ingestion.submit_manifest`. Shape
    mirrors the metadata body constructed by
    :func:`app.services.files.post_file_metadata`, wrapped in the
    Workflow ``executionContext`` envelope.

    All listed inputs are required and non-empty (whitespace-only
    counts as empty); ``description`` is the only optional field — when
    blank it is omitted from the record rather than emitted as ``""``.

    Raises:
        ValueError: if any required input is empty or whitespace-only.
    """
    _require("file_source", file_source)
    _require("file_id", file_id)
    _require("display_name", display_name)
    _require("kind", kind)
    _require("legal_tag", legal_tag)
    _require("acl_owners", acl_owners)
    _require("acl_viewers", acl_viewers)
    _require("data_partition_id", data_partition_id)

    data_block: dict[str, Any] = {
        "Name": display_name,
        "DatasetProperties": {
            "FileSourceInfo": {
                "FileSource": file_source,
                "Name": display_name,
            },
        },
    }
    if description and description.strip():
        data_block["Description"] = description

    dataset_record: dict[str, Any] = {
        "id": file_id,
        "kind": kind,
        "acl": {
            "owners": [acl_owners],
            "viewers": [acl_viewers],
        },
        "legal": {
            "legaltags": [legal_tag],
            "otherRelevantDataCountries": ["US"],
            "status": "compliant",
        },
        "data": data_block,
    }

    return {
        "executionContext": {
            "Payload": {
                "AppKey": "adme-ingestion-tool",
                "data-partition-id": data_partition_id,
            },
            "manifest": {
                "kind": MANIFEST_WRAPPER_KIND,
                "ReferenceData": [],
                "MasterData": [],
                "Data": {
                    "WorkProductComponents": [],
                    "WorkProduct": {},
                    "Datasets": [dataset_record],
                },
            },
        },
    }


def _require(field_name: str, value: str) -> None:
    if not value or not value.strip():
        raise ValueError(
            f"A non-empty {field_name} is required for "
            "build_file_generic_manifest."
        )
