"""OSDU result models for ingestion, workflow tracking, and search.

These dataclasses are the shared contract between the ingestion page
(Judson) and the ingestion / verification services (Kevin). They mirror
the :class:`~app.models.connection.EntitlementsCallResult` style: frozen,
explicit fields, and ``ok`` plus ``latency_ms`` populated on every result
so the UI never has to handle holes.

Do not change field names or types without updating both sides.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
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
