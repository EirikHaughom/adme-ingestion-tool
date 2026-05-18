"""Local SQLite-backed run history for the ADME control plane.

Persists workflow submits + finishes and file-upload events to
``~/.adme-ingestion-tool/run-history.db`` so the History page can show
"what did I do" across Streamlit reruns and TNO-loader / bulk-runner
work that lands in the future.

Contract: see ``.squad/decisions/inbox/satya-run-history-contract.md``.

The DB stores normalized lowercase status strings (``"submitted"`` ·
``"running"`` · ``"finished"`` · ``"failed"``). Readers translate to
:class:`~app.models.osdu.WorkflowStatus` at the boundary so the DB
schema is independent of the Python enum.

All writes wrap a ``with sqlite3.connect(...)`` block (autocommit on
success, rollback on exception). The module opens one short-lived
connection per call — Streamlit reruns + the (future) bulk worker
share nothing through this module's state.
"""

from __future__ import annotations

import os
import sqlite3
from collections.abc import Iterator
from contextlib import closing, contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import TypedDict

from app.models.osdu import RunRow, UploadRow, WorkflowStatus, parse_workflow_status

__all__ = [
    "DBInfo",
    "DEFAULT_DB_PATH",
    "ENV_DB_PATH",
    "RUN_HISTORY_WRITE_ERRORS",
    "VALID_SUBMIT_SOURCES",
    "clear_all",
    "db_info",
    "delete_run",
    "delete_upload",
    "list_file_uploads",
    "list_workflow_runs",
    "purge_older_than",
    "record_file_upload",
    "record_workflow_finish",
    "record_workflow_submit",
]

DEFAULT_DB_PATH: Path = Path.home() / ".adme-ingestion-tool" / "run-history.db"
ENV_DB_PATH = "ADME_RUN_HISTORY_DB"

RUN_HISTORY_WRITE_ERRORS: tuple[type[BaseException], ...] = (
    OSError,
    sqlite3.Error,
    ValueError,
)

VALID_SUBMIT_SOURCES: frozenset[str] = frozenset(
    {"manifest_page", "builder", "bulk_runner", "tno_loader"}
)

_SCHEMA_V1 = """
CREATE TABLE IF NOT EXISTS workflow_runs (
    run_id            TEXT PRIMARY KEY,
    submitted_at      TEXT NOT NULL,
    finished_at       TEXT,
    status            TEXT NOT NULL,
    kind              TEXT,
    correlation_id    TEXT,
    error_message     TEXT,
    latency_ms        INTEGER,
    submit_source     TEXT NOT NULL,
    data_partition_id TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS file_uploads (
    record_id         TEXT PRIMARY KEY,
    uploaded_at       TEXT NOT NULL,
    display_name      TEXT NOT NULL,
    file_source       TEXT NOT NULL,
    size_bytes        INTEGER,
    data_partition_id TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_runs_submitted   ON workflow_runs(submitted_at DESC);
CREATE INDEX IF NOT EXISTS idx_runs_status      ON workflow_runs(status);
CREATE INDEX IF NOT EXISTS idx_runs_partition   ON workflow_runs(data_partition_id);
CREATE INDEX IF NOT EXISTS idx_uploads_when      ON file_uploads(uploaded_at DESC);
CREATE INDEX IF NOT EXISTS idx_uploads_partition ON file_uploads(data_partition_id);
"""


class DBInfo(TypedDict):
    """Diagnostic shape returned by :func:`db_info`."""

    path: str
    size_bytes: int | None
    runs: int
    uploads: int
    user_version: int


# ---------------------------------------------------------------------------
# Connection management + migrations
# ---------------------------------------------------------------------------


def _resolve_db_path() -> Path:
    """Return the configured DB path, honoring the ``ADME_RUN_HISTORY_DB``
    test override."""
    override = os.environ.get(ENV_DB_PATH)
    if override:
        return Path(override)
    return DEFAULT_DB_PATH


def _ensure_parent(path: Path) -> None:
    """Create the parent directory lazily on first write."""
    parent = path.parent
    parent.mkdir(parents=True, exist_ok=True)
    # Best-effort tighten on POSIX; on Windows mkdir mode is mostly ignored.
    if os.name == "posix":
        try:
            os.chmod(parent, 0o700)
        except OSError:
            pass


def _apply_migrations(conn: sqlite3.Connection) -> None:
    """Run schema migrations 0 → current. Currently only v1 exists."""
    current = conn.execute("PRAGMA user_version").fetchone()[0]
    if current < 1:
        conn.executescript(_SCHEMA_V1)
        conn.execute("PRAGMA user_version = 1")


@contextmanager
def _connect() -> Iterator[sqlite3.Connection]:
    """Open the DB, run migrations, yield a row-factory connection.

    Each call opens a fresh short-lived connection — keeps things simple
    across Streamlit reruns and avoids cross-thread sqlite issues.
    """
    path = _resolve_db_path()
    _ensure_parent(path)
    conn = sqlite3.connect(str(path))
    try:
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA foreign_keys = ON")
        _apply_migrations(conn)
        yield conn
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _require_nonempty(name: str, value: str) -> str:
    """Raise ``ValueError`` if *value* is empty/whitespace; return it
    otherwise."""
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")
    return value


def _validate_submit_source(value: str) -> str:
    """Reject unknown ``submit_source`` strings at the service boundary."""
    if value not in VALID_SUBMIT_SOURCES:
        valid = ", ".join(sorted(VALID_SUBMIT_SOURCES))
        raise ValueError(
            f"submit_source must be one of: {valid} (got {value!r})"
        )
    return value


def _clamp_limit(limit: int) -> int:
    """Clamp ``limit`` to ``[1, 10_000]`` per Satya's contract."""
    if limit < 1:
        return 1
    if limit > 10_000:
        return 10_000
    return limit


def _row_to_runrow(row: sqlite3.Row) -> RunRow:
    return RunRow(
        run_id=row["run_id"],
        submitted_at=row["submitted_at"],
        finished_at=row["finished_at"],
        status=parse_workflow_status(row["status"]),
        kind=row["kind"],
        correlation_id=row["correlation_id"],
        error_message=row["error_message"],
        latency_ms=row["latency_ms"],
        submit_source=row["submit_source"],
        data_partition_id=row["data_partition_id"],
    )


def _row_to_uploadrow(row: sqlite3.Row) -> UploadRow:
    return UploadRow(
        record_id=row["record_id"],
        uploaded_at=row["uploaded_at"],
        display_name=row["display_name"],
        file_source=row["file_source"],
        size_bytes=row["size_bytes"],
        data_partition_id=row["data_partition_id"],
    )


# ---------------------------------------------------------------------------
# Writes
# ---------------------------------------------------------------------------


def record_workflow_submit(
    *,
    run_id: str,
    submitted_at: str,
    kind: str | None,
    correlation_id: str | None,
    submit_source: str,
    data_partition_id: str,
) -> None:
    """Record a workflow submit. Status is implicitly ``"submitted"``.

    ``submitted_at`` is caller-supplied (ISO 8601 UTC, e.g.
    ``"2026-05-12T15:00:00Z"``) so tests can pin it. Duplicate
    non-terminal rows refresh their submit metadata; terminal rows are
    preserved so a replayed ``run_id`` cannot erase completion data.
    """
    _require_nonempty("run_id", run_id)
    _require_nonempty("submitted_at", submitted_at)
    _require_nonempty("data_partition_id", data_partition_id)
    _validate_submit_source(submit_source)

    with _connect() as conn, conn:
        conn.execute(
            """
            INSERT INTO workflow_runs (
                run_id, submitted_at, finished_at, status, kind,
                correlation_id, error_message, latency_ms, submit_source,
                data_partition_id
            ) VALUES (?, ?, NULL, 'submitted', ?, ?, NULL, NULL, ?, ?)
            ON CONFLICT(run_id) DO UPDATE SET
                submitted_at = excluded.submitted_at,
                finished_at = NULL,
                status = 'submitted',
                kind = excluded.kind,
                correlation_id = excluded.correlation_id,
                error_message = NULL,
                latency_ms = NULL,
                submit_source = excluded.submit_source,
                data_partition_id = excluded.data_partition_id
            WHERE workflow_runs.status NOT IN ('finished', 'failed')
            """,
            (
                run_id,
                submitted_at,
                kind,
                correlation_id,
                submit_source,
                data_partition_id,
            ),
        )


def record_workflow_finish(
    *,
    run_id: str,
    finished_at: str,
    status: WorkflowStatus,
    latency_ms: int,
    error_message: str | None = None,
) -> None:
    """Update the row for *run_id* with terminal state.

    UPDATEs WHERE run_id = ?. If no row exists (we missed the submit),
    silently no-ops — never insert a finish-only row with NULL
    submitted_at. Non-terminal statuses (IN_PROGRESS / UNKNOWN) no-op.
    """
    _require_nonempty("run_id", run_id)
    _require_nonempty("finished_at", finished_at)

    if status == WorkflowStatus.FINISHED:
        status_str = "finished"
    elif status == WorkflowStatus.FAILED:
        status_str = "failed"
    else:
        return

    with _connect() as conn, conn:
        conn.execute(
            """
            UPDATE workflow_runs
               SET finished_at = ?,
                   status = ?,
                   latency_ms = ?,
                   error_message = ?
             WHERE run_id = ?
            """,
            (finished_at, status_str, latency_ms, error_message, run_id),
        )


def record_file_upload(
    *,
    record_id: str,
    uploaded_at: str,
    display_name: str,
    file_source: str,
    size_bytes: int | None,
    data_partition_id: str,
) -> None:
    """Record a file upload. INSERT OR REPLACE on ``record_id``."""
    _require_nonempty("record_id", record_id)
    _require_nonempty("uploaded_at", uploaded_at)
    _require_nonempty("display_name", display_name)
    _require_nonempty("file_source", file_source)
    _require_nonempty("data_partition_id", data_partition_id)

    with _connect() as conn, conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO file_uploads (
                record_id, uploaded_at, display_name, file_source,
                size_bytes, data_partition_id
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                record_id,
                uploaded_at,
                display_name,
                file_source,
                size_bytes,
                data_partition_id,
            ),
        )


# ---------------------------------------------------------------------------
# Reads
# ---------------------------------------------------------------------------


def list_workflow_runs(
    *,
    limit: int = 100,
    status: WorkflowStatus | None = None,
    since: str | None = None,
    until: str | None = None,
    data_partition_id: str | None = None,
) -> list[RunRow]:
    """Return workflow rows, newest first.

    ``since`` / ``until`` are ISO 8601 UTC bounds applied via
    lexicographic comparison, which is safe because all stored timestamps
    are same-shape Z-suffixed UTC strings.
    """
    limit = _clamp_limit(limit)

    clauses: list[str] = []
    params: list[object] = []
    if status is not None:
        # Map enum → stored string. UNKNOWN is never written; treat as
        # "no rows match" rather than returning everything.
        status_map = {
            WorkflowStatus.IN_PROGRESS: ("submitted", "running"),
            WorkflowStatus.FINISHED: ("finished",),
            WorkflowStatus.FAILED: ("failed",),
            WorkflowStatus.UNKNOWN: (),
        }
        wanted = status_map[status]
        if not wanted:
            return []
        placeholders = ", ".join("?" for _ in wanted)
        clauses.append(f"status IN ({placeholders})")
        params.extend(wanted)
    if since is not None:
        clauses.append("submitted_at >= ?")
        params.append(since)
    if until is not None:
        clauses.append("submitted_at <= ?")
        params.append(until)
    if data_partition_id is not None:
        clauses.append("data_partition_id = ?")
        params.append(data_partition_id)

    where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
    sql = (
        "SELECT run_id, submitted_at, finished_at, status, kind, "
        "correlation_id, error_message, latency_ms, submit_source, "
        f"data_partition_id FROM workflow_runs{where} "
        "ORDER BY submitted_at DESC LIMIT ?"
    )
    params.append(limit)

    with _connect() as conn, closing(conn.execute(sql, params)) as cur:
        return [_row_to_runrow(r) for r in cur.fetchall()]


def list_file_uploads(
    *,
    limit: int = 100,
    since: str | None = None,
    until: str | None = None,
    data_partition_id: str | None = None,
) -> list[UploadRow]:
    """Return file-upload rows, newest first."""
    limit = _clamp_limit(limit)

    clauses: list[str] = []
    params: list[object] = []
    if since is not None:
        clauses.append("uploaded_at >= ?")
        params.append(since)
    if until is not None:
        clauses.append("uploaded_at <= ?")
        params.append(until)
    if data_partition_id is not None:
        clauses.append("data_partition_id = ?")
        params.append(data_partition_id)

    where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
    sql = (
        "SELECT record_id, uploaded_at, display_name, file_source, "
        f"size_bytes, data_partition_id FROM file_uploads{where} "
        "ORDER BY uploaded_at DESC LIMIT ?"
    )
    params.append(limit)

    with _connect() as conn, closing(conn.execute(sql, params)) as cur:
        return [_row_to_uploadrow(r) for r in cur.fetchall()]


# ---------------------------------------------------------------------------
# Deletes / purge
# ---------------------------------------------------------------------------


def delete_run(run_id: str) -> bool:
    """Delete a single workflow row. Returns True if a row was removed."""
    _require_nonempty("run_id", run_id)
    with _connect() as conn, conn:
        cur = conn.execute(
            "DELETE FROM workflow_runs WHERE run_id = ?", (run_id,)
        )
        return cur.rowcount > 0


def delete_upload(record_id: str) -> bool:
    """Delete a single upload row. Returns True if a row was removed."""
    _require_nonempty("record_id", record_id)
    with _connect() as conn, conn:
        cur = conn.execute(
            "DELETE FROM file_uploads WHERE record_id = ?", (record_id,)
        )
        return cur.rowcount > 0


def purge_older_than(*, days: int) -> tuple[int, int]:
    """Delete rows older than *days*. Returns ``(runs, uploads)`` deleted.

    Compares against ``submitted_at`` / ``uploaded_at`` lexicographically
    (safe for Z-suffix UTC). ``days`` must be ``>= 1``.
    """
    if days < 1:
        raise ValueError("days must be >= 1")

    cutoff = datetime.now(tz=UTC).timestamp() - (days * 86_400)
    cutoff_iso = datetime.fromtimestamp(cutoff, tz=UTC).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )

    with _connect() as conn, conn:
        runs_cur = conn.execute(
            "DELETE FROM workflow_runs WHERE submitted_at < ?", (cutoff_iso,)
        )
        uploads_cur = conn.execute(
            "DELETE FROM file_uploads WHERE uploaded_at < ?", (cutoff_iso,)
        )
        return (runs_cur.rowcount, uploads_cur.rowcount)


def clear_all() -> None:
    """Delete every row in both tables. For the Actions tab "Clear all"."""
    with _connect() as conn, conn:
        conn.execute("DELETE FROM workflow_runs")
        conn.execute("DELETE FROM file_uploads")


# ---------------------------------------------------------------------------
# Diagnostics (Actions tab)
# ---------------------------------------------------------------------------


def db_info() -> DBInfo:
    """Return a diagnostic snapshot for the Actions tab.

    Keys: ``path`` (str), ``size_bytes`` (int or None), ``runs`` (int),
    ``uploads`` (int), ``user_version`` (int).
    """
    path = _resolve_db_path()
    size: int | None
    try:
        size = path.stat().st_size
    except OSError:
        size = None

    with _connect() as conn:
        runs = conn.execute(
            "SELECT COUNT(*) FROM workflow_runs"
        ).fetchone()[0]
        uploads = conn.execute(
            "SELECT COUNT(*) FROM file_uploads"
        ).fetchone()[0]
        user_version = conn.execute(
            "PRAGMA user_version"
        ).fetchone()[0]

    return {
        "path": str(path),
        "size_bytes": size,
        "runs": int(runs),
        "uploads": int(uploads),
        "user_version": int(user_version),
    }
