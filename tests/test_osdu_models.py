"""Tests for ``app.models.osdu``: enum, parser, and frozen dataclasses."""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from app.models.osdu import (
    LegalTagCheckResult,
    SearchResult,
    WorkflowRunResult,
    WorkflowStatus,
    parse_workflow_status,
)

# ---------------------------------------------------------------------------
# Enum membership
# ---------------------------------------------------------------------------


def test_workflow_status_has_exactly_the_documented_members() -> None:
    """The contract names four members; nothing more, nothing less."""
    assert {member.name for member in WorkflowStatus} == {
        "IN_PROGRESS",
        "FINISHED",
        "FAILED",
        "UNKNOWN",
    }
    assert WorkflowStatus.IN_PROGRESS.value == "in_progress"
    assert WorkflowStatus.FINISHED.value == "finished"
    assert WorkflowStatus.FAILED.value == "failed"
    assert WorkflowStatus.UNKNOWN.value == "unknown"


def test_workflow_status_is_str_enum() -> None:
    """``WorkflowStatus`` is a ``StrEnum`` so values compare to plain strings."""
    assert WorkflowStatus.IN_PROGRESS == "in_progress"
    assert isinstance(WorkflowStatus.FINISHED, str)


# ---------------------------------------------------------------------------
# parse_workflow_status — every documented mapping
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "raw",
    [
        "running",
        "in progress",
        "in_progress",
        "submitted",
        "queued",
    ],
)
def test_parse_workflow_status_in_progress_values(raw: str) -> None:
    assert parse_workflow_status(raw) == WorkflowStatus.IN_PROGRESS


@pytest.mark.parametrize(
    "raw",
    ["finished", "success", "succeeded", "completed"],
)
def test_parse_workflow_status_finished_values(raw: str) -> None:
    assert parse_workflow_status(raw) == WorkflowStatus.FINISHED


@pytest.mark.parametrize("raw", ["failed", "error"])
def test_parse_workflow_status_failed_values(raw: str) -> None:
    assert parse_workflow_status(raw) == WorkflowStatus.FAILED


@pytest.mark.parametrize(
    "raw",
    [
        "RUNNING",
        "  Running  ",
        "FINISHED",
        "  Finished  ",
        "Failed",
        "ERROR",
        "Submitted",
        "QUEUED",
    ],
)
def test_parse_workflow_status_is_case_and_whitespace_tolerant(raw: str) -> None:
    """Mixed case + leading/trailing whitespace must still resolve."""
    assert parse_workflow_status(raw) is not WorkflowStatus.UNKNOWN


def test_parse_workflow_status_none_returns_unknown() -> None:
    assert parse_workflow_status(None) == WorkflowStatus.UNKNOWN


@pytest.mark.parametrize("raw", ["", "   ", "\t\n"])
def test_parse_workflow_status_blank_returns_unknown(raw: str) -> None:
    assert parse_workflow_status(raw) == WorkflowStatus.UNKNOWN


@pytest.mark.parametrize(
    "raw",
    [
        "weird-status",
        "not_a_real_status",
        "running.",
        "succeded",  # typo
        "ok",
    ],
)
def test_parse_workflow_status_unknown_strings_return_unknown(raw: str) -> None:
    assert parse_workflow_status(raw) == WorkflowStatus.UNKNOWN


# ---------------------------------------------------------------------------
# Frozen dataclass smoke tests
# ---------------------------------------------------------------------------


def test_workflow_run_result_construction_with_required_fields() -> None:
    """Required fields construct cleanly; defaults fill the rest."""
    result = WorkflowRunResult(
        workflow_id="wf-1",
        run_id="run-1",
        status=WorkflowStatus.IN_PROGRESS,
        raw_status="running",
        message=None,
        ok=True,
    )
    assert result.workflow_id == "wf-1"
    assert result.run_id == "run-1"
    assert result.status is WorkflowStatus.IN_PROGRESS
    assert result.raw_status == "running"
    assert result.ok is True
    # Defaults
    assert result.http_status is None
    assert result.latency_ms == 0.0
    assert result.correlation_id is None
    assert result.error_message is None
    assert result.raw_response is None


def test_workflow_run_result_is_frozen() -> None:
    result = WorkflowRunResult(
        workflow_id=None,
        run_id="r",
        status=WorkflowStatus.UNKNOWN,
        raw_status="",
        message=None,
        ok=False,
    )
    with pytest.raises(FrozenInstanceError):
        result.run_id = "other"  # type: ignore[misc]


def test_legal_tag_check_result_construction_and_frozen() -> None:
    result = LegalTagCheckResult(name="foo-tag", ok=True)
    assert result.name == "foo-tag"
    assert result.ok is True
    assert result.http_status is None
    assert result.latency_ms == 0.0
    with pytest.raises(FrozenInstanceError):
        result.ok = False  # type: ignore[misc]


def test_search_result_construction_and_frozen() -> None:
    result = SearchResult(kind="osdu:wks:reference-data:1.0.0", count=3)
    assert result.kind == "osdu:wks:reference-data:1.0.0"
    assert result.count == 3
    assert result.records == []
    assert result.ok is False
    with pytest.raises(FrozenInstanceError):
        result.count = 99  # type: ignore[misc]


def test_search_result_default_records_are_independent_per_instance() -> None:
    """The ``records`` default factory must not share state across instances."""
    a = SearchResult(kind="k", count=0)
    b = SearchResult(kind="k", count=0)
    assert a.records == []
    assert b.records == []
    assert a.records is not b.records
