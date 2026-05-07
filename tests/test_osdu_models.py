"""Tests for ``app.models.osdu``: enum, parser, and frozen dataclasses."""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from app.models.osdu import (
    LegalTag,
    LegalTagCheckResult,
    LegalTagDetailResult,
    LegalTagListResult,
    LegalTagOperationResult,
    LegalTagPropertiesResult,
    LegalTagPropertiesSpec,
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


# ---------------------------------------------------------------------------
# Legal tag dataclasses (frozen + slotted)
# ---------------------------------------------------------------------------


_LEGAL_TAG_CLASSES = [
    LegalTag,
    LegalTagPropertiesSpec,
    LegalTagListResult,
    LegalTagDetailResult,
    LegalTagOperationResult,
    LegalTagPropertiesResult,
]


@pytest.mark.parametrize("cls", _LEGAL_TAG_CLASSES)
def test_legal_tag_dataclass_uses_slots(cls: type) -> None:
    """Every new legal tag dataclass must declare ``__slots__``."""
    assert "__slots__" in vars(cls), (
        f"{cls.__name__} must be declared with slots=True"
    )


def test_legal_tag_construction_with_required_and_default_fields() -> None:
    tag = LegalTag(
        name="opendes-public-test",
        description="Public test tag",
        properties={"countryOfOrigin": ["US"]},
    )
    assert tag.name == "opendes-public-test"
    assert tag.description == "Public test tag"
    assert tag.properties == {"countryOfOrigin": ["US"]}
    # Optional ``is_valid`` defaults to None (server omitted the flag).
    assert tag.is_valid is None


def test_legal_tag_is_frozen() -> None:
    tag = LegalTag(name="t", description="", properties={})
    with pytest.raises(FrozenInstanceError):
        tag.name = "other"  # type: ignore[misc]


def test_legal_tag_properties_spec_defaults_are_empty_lists() -> None:
    spec = LegalTagPropertiesSpec()
    assert spec.country_of_origin == []
    assert spec.other_relevant_data_countries == []
    assert spec.security_classifications == []
    assert spec.export_classifications == []
    assert spec.personal_data_types == []
    assert spec.data_types == []


def test_legal_tag_properties_spec_defaults_are_per_instance() -> None:
    a = LegalTagPropertiesSpec()
    b = LegalTagPropertiesSpec()
    assert a.country_of_origin is not b.country_of_origin


def test_legal_tag_properties_spec_construction_with_values() -> None:
    spec = LegalTagPropertiesSpec(
        country_of_origin=["US", "CA"],
        data_types=["Public Domain Data"],
        security_classifications=["Public", "Private"],
    )
    assert spec.country_of_origin == ["US", "CA"]
    assert spec.data_types == ["Public Domain Data"]
    assert spec.security_classifications == ["Public", "Private"]


def test_legal_tag_properties_spec_is_frozen() -> None:
    spec = LegalTagPropertiesSpec()
    with pytest.raises(FrozenInstanceError):
        spec.country_of_origin = ["US"]  # type: ignore[misc]


def test_legal_tag_list_result_defaults_and_construction() -> None:
    result = LegalTagListResult()
    assert result.items == []
    assert result.ok is False
    assert result.http_status is None
    assert result.latency_ms == 0.0
    assert result.correlation_id is None
    assert result.error_message is None
    assert result.raw_response is None


def test_legal_tag_list_result_with_items() -> None:
    items = [LegalTag(name="t1", description="", properties={})]
    result = LegalTagListResult(items=items, ok=True, http_status=200)
    assert result.items is items
    assert result.ok is True
    assert result.http_status == 200


def test_legal_tag_list_result_is_frozen() -> None:
    result = LegalTagListResult()
    with pytest.raises(FrozenInstanceError):
        result.ok = True  # type: ignore[misc]


def test_legal_tag_detail_result_construction_and_frozen() -> None:
    tag = LegalTag(name="t", description="", properties={})
    result = LegalTagDetailResult(tag=tag, ok=True, http_status=200)
    assert result.tag is tag
    assert result.ok is True
    # Defaults
    empty = LegalTagDetailResult(tag=None)
    assert empty.tag is None
    assert empty.ok is False
    assert empty.latency_ms == 0.0
    with pytest.raises(FrozenInstanceError):
        result.ok = False  # type: ignore[misc]


def test_legal_tag_operation_result_construction_and_frozen() -> None:
    result = LegalTagOperationResult(
        name="opendes-tag", ok=True, http_status=204
    )
    assert result.name == "opendes-tag"
    assert result.ok is True
    assert result.http_status == 204
    # Defaults
    empty = LegalTagOperationResult(name="x")
    assert empty.ok is False
    assert empty.http_status is None
    assert empty.correlation_id is None
    with pytest.raises(FrozenInstanceError):
        result.ok = False  # type: ignore[misc]


def test_legal_tag_properties_result_construction_and_frozen() -> None:
    spec = LegalTagPropertiesSpec(country_of_origin=["US"])
    result = LegalTagPropertiesResult(spec=spec, ok=True, http_status=200)
    assert result.spec is spec
    assert result.ok is True
    # Defaults
    empty = LegalTagPropertiesResult(spec=None)
    assert empty.spec is None
    assert empty.ok is False
    assert empty.error_message is None
    with pytest.raises(FrozenInstanceError):
        result.ok = False  # type: ignore[misc]

