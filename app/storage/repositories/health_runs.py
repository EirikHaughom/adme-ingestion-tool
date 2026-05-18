"""Repository for persisted ADME health validation runs."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.models.connection import ServiceHealthResult
from app.storage.config import resolve_storage_config
from app.storage.engine import create_engine_from_config
from app.storage.migrations import ensure_storage_ready
from app.storage.models import (
    ConnectionProfileRow,
    HealthRunResultRow,
    HealthRunRow,
    utc_now,
)
from app.storage.repositories.connection_profiles import ConnectionProfileRepository
from app.storage.session import create_session_factory, session_scope


@dataclass(frozen=True)
class HealthRunSummary:
    """Domain summary for one persisted health validation run."""

    id: str
    profile_id: str
    checked_at: datetime
    overall_state: str
    healthy_count: int
    unhealthy_count: int
    error_count: int
    results: tuple[ServiceHealthResult, ...]


class HealthRunRepository:
    """Transaction-scoped repository for health run persistence."""

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def record_run(
        self,
        profile_id: str,
        results: Sequence[ServiceHealthResult],
        *,
        checked_at: datetime | None = None,
    ) -> HealthRunSummary:
        """Persist one health run and all service-level results atomically."""
        checked_at = _normalize_datetime(checked_at) or utc_now()
        result_rows = list(results)
        healthy_count = sum(result.status == "healthy" for result in result_rows)
        unhealthy_count = sum(result.status == "unhealthy" for result in result_rows)
        error_count = sum(result.status == "error" for result in result_rows)
        overall_state = _overall_state(
            total_count=len(result_rows),
            unhealthy_count=unhealthy_count,
            error_count=error_count,
        )

        with session_scope(self._session_factory) as session:
            profile = session.get(ConnectionProfileRow, profile_id)
            if profile is None or profile.deleted_at is not None:
                raise ValueError("Health run must reference an existing profile.")

            run = HealthRunRow(
                id=uuid4().hex,
                profile_id=profile_id,
                checked_at=checked_at,
                overall_state=overall_state,
                healthy_count=healthy_count,
                unhealthy_count=unhealthy_count,
                error_count=error_count,
            )
            session.add(run)
            for service_order, result in enumerate(result_rows):
                session.add(
                    HealthRunResultRow(
                        id=uuid4().hex,
                        run_id=run.id,
                        service_order=service_order,
                        service_name=result.service_name,
                        path=result.path,
                        status=result.status,
                        status_code=result.status_code,
                        response_time_ms=result.response_time_ms,
                        error_message=result.error_message,
                    )
                )

            session.flush()
            return _summary_from_row(run)

    def get_latest_for_profile(self, profile_id: str) -> HealthRunSummary | None:
        """Return the most recent health run for a profile."""
        with session_scope(self._session_factory) as session:
            run = session.scalar(
                select(HealthRunRow)
                .where(HealthRunRow.profile_id == profile_id)
                .order_by(HealthRunRow.checked_at.desc(), HealthRunRow.id.desc())
                .limit(1)
            )
            if run is None:
                return None
            return _summary_from_row(run)


def record_health_run(
    connection: object,
    results: Sequence[ServiceHealthResult],
    *,
    checked_at: datetime | None = None,
) -> HealthRunSummary:
    """Record a health run for the active profile using resolved storage."""
    result_rows = list(results)
    config = resolve_storage_config()
    ensure_storage_ready(config)
    engine = create_engine_from_config(config)
    try:
        session_factory = create_session_factory(engine)
        profile_repository = ConnectionProfileRepository(session_factory)
        active_profile = profile_repository.get_active_profile()
        if active_profile is None:
            raise ValueError("Health run requires an active connection profile.")
        return HealthRunRepository(session_factory).record_run(
            active_profile.id,
            result_rows,
            checked_at=checked_at,
        )
    finally:
        engine.dispose()


def load_latest_health_run(
    connection: object | None = None,
) -> HealthRunSummary | None:
    """Load the latest health run for the active profile using resolved storage."""
    config = resolve_storage_config()
    ensure_storage_ready(config)
    engine = create_engine_from_config(config)
    try:
        session_factory = create_session_factory(engine)
        profile_repository = ConnectionProfileRepository(session_factory)
        active_profile = profile_repository.get_active_profile()
        if active_profile is None:
            return None
        return HealthRunRepository(session_factory).get_latest_for_profile(
            active_profile.id
        )
    finally:
        engine.dispose()


def _overall_state(
    *,
    total_count: int,
    unhealthy_count: int,
    error_count: int,
) -> str:
    if total_count == 0:
        return "not_tested"
    if error_count:
        return "error"
    if unhealthy_count:
        return "degraded"
    return "healthy"


def _summary_from_row(row: HealthRunRow) -> HealthRunSummary:
    return HealthRunSummary(
        id=row.id,
        profile_id=row.profile_id,
        checked_at=_normalize_datetime(row.checked_at) or row.checked_at,
        overall_state=row.overall_state,
        healthy_count=row.healthy_count,
        unhealthy_count=row.unhealthy_count,
        error_count=row.error_count,
        results=tuple(
            ServiceHealthResult(
                service_name=result.service_name,
                path=result.path,
                status=result.status,
                status_code=result.status_code,
                response_time_ms=result.response_time_ms,
                error_message=result.error_message,
            )
            for result in row.results
        ),
    )


def _normalize_datetime(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
