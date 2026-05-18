"""OSDU result models for ingestion, workflow tracking, and search.

These dataclasses are the shared contract between the ingestion page
(Judson) and the ingestion / verification services (Kevin). They mirror
the :class:`~app.models.connection.EntitlementsCallResult` style: frozen,
explicit fields, and ``ok`` plus ``latency_ms`` populated on every result
so the UI never has to handle holes.

Do not change field names or types without updating both sides.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from pathlib import Path
from typing import Any


class WorkflowStatus(StrEnum):
    """Normalized workflow run status used by the UI status branches."""

    IN_PROGRESS = "in_progress"
    FINISHED = "finished"
    FAILED = "failed"
    UNKNOWN = "unknown"


_IN_PROGRESS_VALUES: frozenset[str] = frozenset(
    {"running", "in progress", "in_progress", "submitted", "queued"}
)
_FINISHED_VALUES: frozenset[str] = frozenset(
    {"finished", "success", "succeeded", "completed"}
)
_FAILED_VALUES: frozenset[str] = frozenset({"failed", "error"})


def parse_workflow_status(raw: str | None) -> WorkflowStatus:
    """Normalize the server-supplied status string.

    Mapping (case-insensitive, whitespace-trimmed):
      ``running``, ``in progress``, ``in_progress``, ``submitted``,
      ``queued``                                       -> IN_PROGRESS
      ``finished``, ``success``, ``succeeded``,
      ``completed``                                    -> FINISHED
      ``failed``, ``error``                            -> FAILED
      ``None``, ``""``, anything else                  -> UNKNOWN
    """
    if raw is None:
        return WorkflowStatus.UNKNOWN
    normalized = raw.strip().lower()
    if not normalized:
        return WorkflowStatus.UNKNOWN
    if normalized in _IN_PROGRESS_VALUES:
        return WorkflowStatus.IN_PROGRESS
    if normalized in _FINISHED_VALUES:
        return WorkflowStatus.FINISHED
    if normalized in _FAILED_VALUES:
        return WorkflowStatus.FAILED
    return WorkflowStatus.UNKNOWN


@dataclass(frozen=True)
class WorkflowRunResult:
    """Outcome of a single workflow submit or status call.

    ``status`` is the normalized enum the page branches on; ``raw_status``
    is the verbatim server string, surfaced in captions so operators see
    what the workflow service actually said.
    """

    workflow_id: str | None
    run_id: str | None
    status: WorkflowStatus
    raw_status: str
    message: str | None
    ok: bool
    http_status: int | None = None
    latency_ms: float = 0.0
    correlation_id: str | None = None
    error_message: str | None = None
    raw_response: dict | str | None = None


@dataclass(frozen=True)
class LegalTagCheckResult:
    """Outcome of a single ``GET /api/legal/v1/legaltags/{name}`` probe."""

    name: str
    ok: bool
    http_status: int | None = None
    latency_ms: float = 0.0
    correlation_id: str | None = None
    error_message: str | None = None


@dataclass(frozen=True)
class SearchResult:
    """Outcome of a single ``POST /api/search/v2/query`` call."""

    kind: str
    count: int
    records: list[dict] = field(default_factory=list)
    ok: bool = False
    http_status: int | None = None
    latency_ms: float = 0.0
    correlation_id: str | None = None
    error_message: str | None = None


@dataclass(frozen=True, slots=True)
class RecordSummary:
    """One hit from ``POST /api/search/v2/query`` projected for list views.

    ``source`` is the raw record block (or ``returnedFields`` projection)
    the server included for this hit; the page renders a truncated
    preview from it. Times are passed through verbatim as ISO-8601
    strings so we never lose precision rounding through ``datetime``.
    """

    id: str
    kind: str
    create_time: str | None = None
    version: int | None = None
    source: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class SearchPageResult:
    """Outcome of one Search-v2 ``/query`` page request."""

    kind: str
    query: str | None = None
    offset: int = 0
    limit: int = 0
    records: list[RecordSummary] = field(default_factory=list)
    total_count: int | None = None
    has_more: bool = False
    ok: bool = False
    http_status: int | None = None
    latency_ms: float = 0.0
    correlation_id: str | None = None
    error_message: str | None = None
    raw_response: dict | str | None = None


@dataclass(frozen=True, slots=True)
class KindAggregationResult:
    """Outcome of the kinds-discovery call.

    ``from_aggregation`` is ``True`` when Search aggregation supplied the
    list and ``False`` when we fell back to sampling the first page of
    records and extracting unique kinds (Darryl's option B-equivalent).
    """

    kinds: list[str] = field(default_factory=list)
    from_aggregation: bool = True
    ok: bool = False
    http_status: int | None = None
    latency_ms: float = 0.0
    correlation_id: str | None = None
    error_message: str | None = None
    raw_response: dict | str | None = None


@dataclass(frozen=True, slots=True)
class RecordDetailResult:
    """Outcome of ``GET /api/storage/v2/records/{id}``."""

    record_id: str
    record: dict | None = None
    ok: bool = False
    http_status: int | None = None
    latency_ms: float = 0.0
    correlation_id: str | None = None
    error_message: str | None = None
    raw_response: dict | str | None = None


@dataclass(frozen=True, slots=True)
class LegalTag:
    """A single legal tag as returned by the ADME Legal service.

    ``is_valid`` mirrors the optional server-supplied ``isValid`` flag
    on list responses; ``None`` means the server did not include it.
    """

    name: str
    description: str
    properties: dict[str, Any]
    is_valid: bool | None = None


@dataclass(frozen=True, slots=True)
class LegalTagPropertiesSpec:
    """Allowed values for the partition, used to populate dropdowns.

    Server-key normalization is owned by
    :mod:`app.services.legal_tags`. Country fields accept both the
    documented dict shape (alpha-2 → display name) and the legacy list
    shape; classification fields likewise accept either spelling.
    """

    country_of_origin: list[str] = field(default_factory=list)
    other_relevant_data_countries: list[str] = field(default_factory=list)
    security_classifications: list[str] = field(default_factory=list)
    export_classifications: list[str] = field(default_factory=list)
    personal_data_types: list[str] = field(default_factory=list)
    data_types: list[str] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class LegalTagListResult:
    """Outcome of ``GET /api/legal/v1/legaltags``."""

    items: list[LegalTag] = field(default_factory=list)
    ok: bool = False
    http_status: int | None = None
    latency_ms: float = 0.0
    correlation_id: str | None = None
    error_message: str | None = None
    raw_response: dict | str | None = None


@dataclass(frozen=True, slots=True)
class LegalTagDetailResult:
    """Outcome of GET-one / POST / PUT against the Legal service."""

    tag: LegalTag | None
    ok: bool = False
    http_status: int | None = None
    latency_ms: float = 0.0
    correlation_id: str | None = None
    error_message: str | None = None
    raw_response: dict | str | None = None


@dataclass(frozen=True, slots=True)
class LegalTagOperationResult:
    """Outcome of ``DELETE /api/legal/v1/legaltags/{name}``."""

    name: str
    ok: bool = False
    http_status: int | None = None
    latency_ms: float = 0.0
    correlation_id: str | None = None
    error_message: str | None = None
    raw_response: dict | str | None = None


@dataclass(frozen=True, slots=True)
class LegalTagPropertiesResult:
    """Outcome of ``GET /api/legal/v1/legaltags:properties``."""

    spec: LegalTagPropertiesSpec | None
    ok: bool = False
    http_status: int | None = None
    latency_ms: float = 0.0
    correlation_id: str | None = None
    error_message: str | None = None
    raw_response: dict | str | None = None


@dataclass(frozen=True, slots=True)
class UploadURLResult:
    """Outcome of ``GET /api/file/v2/files/uploadURL``.

    ``signed_url`` is the Azure Blob SAS URL returned by ADME; treat as a
    credential and never log the query string. ``file_source`` is the
    opaque value to echo back in the metadata POST body.
    """

    ok: bool = False
    http_status: int | None = None
    latency_ms: float = 0.0
    correlation_id: str | None = None
    error_message: str | None = None
    signed_url: str | None = None
    file_source: str | None = None
    file_id: str | None = None


@dataclass(frozen=True, slots=True)
class UploadBytesResult:
    """Outcome of the ``PUT`` to the Azure Blob signed URL.

    NOTE: No ``correlation_id`` field by design — this call goes directly
    to Azure Blob Storage via the SAS-signed URL, not through ADME, and
    Azure does not emit an ADME correlation header.
    """

    ok: bool = False
    http_status: int | None = None
    latency_ms: float = 0.0
    error_message: str | None = None
    bytes_uploaded: int = 0


@dataclass(frozen=True, slots=True)
class FileMetadataResult:
    """Outcome of ``POST /api/file/v2/files/metadata``."""

    ok: bool = False
    http_status: int | None = None
    latency_ms: float = 0.0
    correlation_id: str | None = None
    error_message: str | None = None
    record_id: str | None = None
    record_version: int | None = None


@dataclass(frozen=True, slots=True)
class DatasetTier:
    """One tier (reference-data / master-data / work-products) of a dataset.

    Either ``manifest_glob`` is set (enabled tier with manifests to walk)
    or ``reason`` is set (disabled tier with a human-readable explanation
    surfaced in the page). ``description`` is optional UI copy.
    """

    enabled: bool
    manifest_glob: str | None = None
    description: str | None = None
    reason: str | None = None


@dataclass(frozen=True, slots=True)
class DatasetDescriptor:
    """A Bulk Load dataset registered on disk under ``app/data/datasets/``.

    ``root_dir`` is the absolute path to the dataset folder; relative
    ``manifest_glob`` and ``notice_path`` values are resolved against
    it. ``tiers`` is keyed by tier name (``reference-data`` etc.).
    """

    id: str
    display_name: str
    source_url: str
    notice_path: str
    tiers: Mapping[str, DatasetTier]
    root_dir: Path


@dataclass(frozen=True, slots=True)
class ManifestPreview:
    """A single manifest file inspected by ``preview_tier`` (no network).

    ``record_section`` is the OSDU manifest section the records were
    counted from (``ReferenceData``, ``MasterData``, or ``Data`` for
    work-products).
    """

    path: Path
    filename: str
    kind: str
    record_count: int
    record_section: str


@dataclass(frozen=True, slots=True)
class SubmitResult:
    """Outcome of one manifest submit inside ``submit_tier``.

    ``status`` is ``"success"`` when ``submit_manifest`` returned a run
    id and ``"error"`` otherwise. ``run_id`` and ``record_id`` are the
    server-supplied identifiers from the workflow response when
    available.
    """

    manifest_path: Path
    filename: str
    status: str
    run_id: str | None
    record_id: str | None
    error: str | None
    submitted_at: datetime


@dataclass(frozen=True, slots=True)
class RunRow:
    """One row from ``workflow_runs`` in the local run-history DB.

    See :mod:`app.services.run_history`. ``status`` is the parsed enum;
    ``submitted_at`` / ``finished_at`` are ISO 8601 UTC strings (Z-suffix).
    ``submit_source`` is one of ``"manifest_page" | "builder" |
    "bulk_runner" | "tno_loader" | "bulk_load"``.
    """

    run_id: str
    submitted_at: str
    finished_at: str | None
    status: WorkflowStatus
    kind: str | None
    correlation_id: str | None
    error_message: str | None
    latency_ms: int | None
    submit_source: str
    data_partition_id: str


@dataclass(frozen=True, slots=True)
class UploadRow:
    """One row from ``file_uploads`` in the local run-history DB."""

    record_id: str
    uploaded_at: str
    display_name: str
    file_source: str
    size_bytes: int | None
    data_partition_id: str
