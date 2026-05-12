"""Tests for ``app.services.run_history``."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from app.models.osdu import RunRow, UploadRow, WorkflowStatus
from app.services import run_history


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _seed_run(
    run_id: str = "r1",
    *,
    submitted_at: str = "2026-05-12T15:00:00Z",
    kind: str | None = "osdu:wks:Manifest:1.0.0",
    correlation_id: str | None = "corr-1",
    submit_source: str = "manifest_page",
    data_partition_id: str = "opendes",
) -> None:
    run_history.record_workflow_submit(
        run_id=run_id,
        submitted_at=submitted_at,
        kind=kind,
        correlation_id=correlation_id,
        submit_source=submit_source,
        data_partition_id=data_partition_id,
    )


def _seed_upload(
    record_id: str = "u1",
    *,
    uploaded_at: str = "2026-05-12T15:00:00Z",
    display_name: str = "foo.csv",
    file_source: str = "/staging/foo",
    size_bytes: int | None = 1234,
    data_partition_id: str = "opendes",
) -> None:
    run_history.record_file_upload(
        record_id=record_id,
        uploaded_at=uploaded_at,
        display_name=display_name,
        file_source=file_source,
        size_bytes=size_bytes,
        data_partition_id=data_partition_id,
    )


# ---------------------------------------------------------------------------
# Schema + initialization
# ---------------------------------------------------------------------------


def test_first_write_creates_db_file_and_parent_dir(
    run_history_tmp_db: Path,
) -> None:
    assert not run_history_tmp_db.exists()
    _seed_run()
    assert run_history_tmp_db.exists()
    assert run_history_tmp_db.parent.is_dir()


def test_schema_user_version_is_one(run_history_tmp_db: Path) -> None:
    _seed_run()
    with sqlite3.connect(str(run_history_tmp_db)) as conn:
        version = conn.execute("PRAGMA user_version").fetchone()[0]
    assert version == 1


def test_schema_includes_expected_tables_and_indexes(
    run_history_tmp_db: Path,
) -> None:
    _seed_run()
    with sqlite3.connect(str(run_history_tmp_db)) as conn:
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        indexes = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='index'"
            )
        }
    assert {"workflow_runs", "file_uploads"} <= tables
    expected_indexes = {
        "idx_runs_submitted",
        "idx_runs_status",
        "idx_runs_partition",
        "idx_uploads_when",
        "idx_uploads_partition",
    }
    assert expected_indexes <= indexes


def test_empty_db_returns_empty_lists(run_history_tmp_db: Path) -> None:
    assert run_history.list_workflow_runs() == []
    assert run_history.list_file_uploads() == []


# ---------------------------------------------------------------------------
# Validation at boundary
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "field",
    ["run_id", "submitted_at", "data_partition_id"],
)
def test_record_workflow_submit_rejects_empty_required_field(
    run_history_tmp_db: Path, field: str
) -> None:
    payload: dict[str, object] = {
        "run_id": "r1",
        "submitted_at": "2026-05-12T15:00:00Z",
        "kind": None,
        "correlation_id": None,
        "submit_source": "manifest_page",
        "data_partition_id": "opendes",
    }
    payload[field] = ""
    with pytest.raises(ValueError):
        run_history.record_workflow_submit(**payload)  # type: ignore[arg-type]


def test_record_workflow_submit_rejects_unknown_submit_source(
    run_history_tmp_db: Path,
) -> None:
    with pytest.raises(ValueError):
        run_history.record_workflow_submit(
            run_id="r1",
            submitted_at="2026-05-12T15:00:00Z",
            kind=None,
            correlation_id=None,
            submit_source="not_a_source",
            data_partition_id="opendes",
        )


@pytest.mark.parametrize(
    "source",
    ["manifest_page", "builder", "bulk_runner", "tno_loader"],
)
def test_record_workflow_submit_accepts_each_locked_source(
    run_history_tmp_db: Path, source: str
) -> None:
    _seed_run(run_id=f"r-{source}", submit_source=source)
    rows = run_history.list_workflow_runs()
    assert any(r.submit_source == source for r in rows)


@pytest.mark.parametrize(
    "field",
    ["record_id", "uploaded_at", "display_name", "file_source", "data_partition_id"],
)
def test_record_file_upload_rejects_empty_required_field(
    run_history_tmp_db: Path, field: str
) -> None:
    payload: dict[str, object] = {
        "record_id": "u1",
        "uploaded_at": "2026-05-12T15:00:00Z",
        "display_name": "foo.csv",
        "file_source": "/staging/foo",
        "size_bytes": 100,
        "data_partition_id": "opendes",
    }
    payload[field] = ""
    with pytest.raises(ValueError):
        run_history.record_file_upload(**payload)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Round-trip: submit → list
# ---------------------------------------------------------------------------


def test_round_trip_workflow_submit(run_history_tmp_db: Path) -> None:
    _seed_run(
        run_id="r-42",
        submitted_at="2026-05-12T15:00:00Z",
        kind="osdu:wks:Manifest:1.0.0",
        correlation_id="corr-42",
        submit_source="builder",
        data_partition_id="opendes",
    )
    rows = run_history.list_workflow_runs()
    assert len(rows) == 1
    row = rows[0]
    assert isinstance(row, RunRow)
    assert row.run_id == "r-42"
    assert row.submitted_at == "2026-05-12T15:00:00Z"
    assert row.finished_at is None
    assert row.status == WorkflowStatus.IN_PROGRESS  # "submitted"
    assert row.kind == "osdu:wks:Manifest:1.0.0"
    assert row.correlation_id == "corr-42"
    assert row.submit_source == "builder"
    assert row.data_partition_id == "opendes"
    assert row.latency_ms is None
    assert row.error_message is None


def test_round_trip_file_upload(run_history_tmp_db: Path) -> None:
    _seed_upload(
        record_id="opendes:dataset--File.Generic:abc",
        uploaded_at="2026-05-12T16:00:00Z",
        display_name="well.las",
        file_source="/staging/well",
        size_bytes=4096,
        data_partition_id="opendes",
    )
    rows = run_history.list_file_uploads()
    assert len(rows) == 1
    row = rows[0]
    assert isinstance(row, UploadRow)
    assert row.record_id == "opendes:dataset--File.Generic:abc"
    assert row.display_name == "well.las"
    assert row.size_bytes == 4096


# ---------------------------------------------------------------------------
# Finish updates row
# ---------------------------------------------------------------------------


def test_record_workflow_finish_updates_existing_row_finished(
    run_history_tmp_db: Path,
) -> None:
    _seed_run(run_id="r1")
    run_history.record_workflow_finish(
        run_id="r1",
        finished_at="2026-05-12T15:10:00Z",
        status=WorkflowStatus.FINISHED,
        latency_ms=600_000,
    )
    rows = run_history.list_workflow_runs()
    assert rows[0].status == WorkflowStatus.FINISHED
    assert rows[0].finished_at == "2026-05-12T15:10:00Z"
    assert rows[0].latency_ms == 600_000


def test_record_workflow_finish_updates_existing_row_failed(
    run_history_tmp_db: Path,
) -> None:
    _seed_run(run_id="r1")
    run_history.record_workflow_finish(
        run_id="r1",
        finished_at="2026-05-12T15:10:00Z",
        status=WorkflowStatus.FAILED,
        latency_ms=42_000,
        error_message="boom",
    )
    rows = run_history.list_workflow_runs()
    assert rows[0].status == WorkflowStatus.FAILED
    assert rows[0].error_message == "boom"


def test_record_workflow_finish_no_op_when_row_missing(
    run_history_tmp_db: Path,
) -> None:
    # Finish-only call should NOT insert a phantom row.
    run_history.record_workflow_finish(
        run_id="ghost",
        finished_at="2026-05-12T15:10:00Z",
        status=WorkflowStatus.FINISHED,
        latency_ms=1,
    )
    assert run_history.list_workflow_runs() == []


def test_record_workflow_finish_ignores_non_terminal_status(
    run_history_tmp_db: Path,
) -> None:
    _seed_run(run_id="r1")
    run_history.record_workflow_finish(
        run_id="r1",
        finished_at="2026-05-12T15:10:00Z",
        status=WorkflowStatus.IN_PROGRESS,
        latency_ms=1000,
    )
    row = run_history.list_workflow_runs()[0]
    assert row.finished_at is None
    assert row.status == WorkflowStatus.IN_PROGRESS  # still "submitted"


# ---------------------------------------------------------------------------
# Filters
# ---------------------------------------------------------------------------


def test_list_workflow_runs_filters_by_partition(
    run_history_tmp_db: Path,
) -> None:
    _seed_run(run_id="r-opendes", data_partition_id="opendes")
    _seed_run(run_id="r-other", data_partition_id="other")
    rows = run_history.list_workflow_runs(data_partition_id="opendes")
    assert [r.run_id for r in rows] == ["r-opendes"]


def test_list_workflow_runs_filters_by_status(
    run_history_tmp_db: Path,
) -> None:
    _seed_run(run_id="r-pending")
    _seed_run(run_id="r-done", submitted_at="2026-05-12T15:01:00Z")
    run_history.record_workflow_finish(
        run_id="r-done",
        finished_at="2026-05-12T15:05:00Z",
        status=WorkflowStatus.FINISHED,
        latency_ms=240_000,
    )
    finished = run_history.list_workflow_runs(status=WorkflowStatus.FINISHED)
    in_progress = run_history.list_workflow_runs(
        status=WorkflowStatus.IN_PROGRESS
    )
    assert [r.run_id for r in finished] == ["r-done"]
    assert [r.run_id for r in in_progress] == ["r-pending"]


def test_list_workflow_runs_filters_by_since(
    run_history_tmp_db: Path,
) -> None:
    _seed_run(run_id="r-old", submitted_at="2026-04-01T00:00:00Z")
    _seed_run(run_id="r-new", submitted_at="2026-05-12T00:00:00Z")
    rows = run_history.list_workflow_runs(since="2026-05-01T00:00:00Z")
    assert [r.run_id for r in rows] == ["r-new"]


def test_list_workflow_runs_honors_limit_and_orders_desc(
    run_history_tmp_db: Path,
) -> None:
    for i in range(5):
        _seed_run(
            run_id=f"r-{i}",
            submitted_at=f"2026-05-12T15:0{i}:00Z",
        )
    rows = run_history.list_workflow_runs(limit=3)
    assert [r.run_id for r in rows] == ["r-4", "r-3", "r-2"]


def test_list_file_uploads_filters_by_partition(
    run_history_tmp_db: Path,
) -> None:
    _seed_upload(record_id="u-a", data_partition_id="opendes")
    _seed_upload(record_id="u-b", data_partition_id="other")
    rows = run_history.list_file_uploads(data_partition_id="opendes")
    assert [r.record_id for r in rows] == ["u-a"]


def test_list_workflow_runs_unknown_status_returns_empty(
    run_history_tmp_db: Path,
) -> None:
    _seed_run()
    rows = run_history.list_workflow_runs(status=WorkflowStatus.UNKNOWN)
    assert rows == []


# ---------------------------------------------------------------------------
# Delete + purge
# ---------------------------------------------------------------------------


def test_delete_run_returns_true_when_removed(
    run_history_tmp_db: Path,
) -> None:
    _seed_run(run_id="r1")
    assert run_history.delete_run("r1") is True
    assert run_history.delete_run("r1") is False
    assert run_history.list_workflow_runs() == []


def test_delete_upload_returns_true_when_removed(
    run_history_tmp_db: Path,
) -> None:
    _seed_upload(record_id="u1")
    assert run_history.delete_upload("u1") is True
    assert run_history.delete_upload("u1") is False


def test_purge_older_than_returns_counts_and_only_deletes_old_rows(
    run_history_tmp_db: Path,
) -> None:
    _seed_run(run_id="r-old", submitted_at="2020-01-01T00:00:00Z")
    _seed_run(run_id="r-new", submitted_at="2999-01-01T00:00:00Z")
    _seed_upload(record_id="u-old", uploaded_at="2020-01-01T00:00:00Z")
    _seed_upload(record_id="u-new", uploaded_at="2999-01-01T00:00:00Z")

    runs_deleted, uploads_deleted = run_history.purge_older_than(days=30)
    assert runs_deleted == 1
    assert uploads_deleted == 1

    remaining_runs = {r.run_id for r in run_history.list_workflow_runs()}
    remaining_uploads = {r.record_id for r in run_history.list_file_uploads()}
    assert remaining_runs == {"r-new"}
    assert remaining_uploads == {"u-new"}


def test_purge_older_than_rejects_zero_or_negative_days(
    run_history_tmp_db: Path,
) -> None:
    with pytest.raises(ValueError):
        run_history.purge_older_than(days=0)
    with pytest.raises(ValueError):
        run_history.purge_older_than(days=-1)


def test_clear_all_removes_every_row(run_history_tmp_db: Path) -> None:
    _seed_run(run_id="r1")
    _seed_upload(record_id="u1")
    run_history.clear_all()
    assert run_history.list_workflow_runs() == []
    assert run_history.list_file_uploads() == []


# ---------------------------------------------------------------------------
# Idempotent re-upload + re-submit (INSERT OR REPLACE)
# ---------------------------------------------------------------------------


def test_record_file_upload_replaces_existing_record_id(
    run_history_tmp_db: Path,
) -> None:
    _seed_upload(record_id="u1", display_name="v1.csv")
    _seed_upload(record_id="u1", display_name="v2.csv")
    rows = run_history.list_file_uploads()
    assert len(rows) == 1
    assert rows[0].display_name == "v2.csv"


# ---------------------------------------------------------------------------
# db_info
# ---------------------------------------------------------------------------


def test_db_info_reports_counts_and_version(
    run_history_tmp_db: Path,
) -> None:
    _seed_run(run_id="r1")
    _seed_upload(record_id="u1")
    _seed_upload(record_id="u2")
    info = run_history.db_info()
    assert info["runs"] == 1
    assert info["uploads"] == 2
    assert info["user_version"] == 1
    assert info["path"] == str(run_history_tmp_db)
    assert isinstance(info["size_bytes"], int)
    assert info["size_bytes"] > 0
