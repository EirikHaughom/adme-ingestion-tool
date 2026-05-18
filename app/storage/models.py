"""SQLAlchemy ORM rows for the storage boundary."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import DateTime, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utc_now() -> datetime:
    """Return an aware UTC timestamp for Python-side defaults."""
    return datetime.now(UTC)


class Base(DeclarativeBase):
    """Declarative base for storage tables."""


class ConnectionProfileRow(Base):
    """Non-secret ADME connection profile row."""

    __tablename__ = "connection_profiles"
    __table_args__ = (
        Index(
            "ix_connection_profiles_deleted_display_id",
            "deleted_at",
            "display_name",
            "id",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    endpoint: Mapped[str] = mapped_column(Text, nullable=False)
    tenant_id: Mapped[str] = mapped_column(String(255), nullable=False)
    client_id: Mapped[str] = mapped_column(String(255), nullable=False)
    data_partition_id: Mapped[str] = mapped_column(String(255), nullable=False)
    token_scope: Mapped[str] = mapped_column(String(1024), nullable=False)
    auth_method: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
        nullable=False,
    )
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )


class ActiveProfileRow(Base):
    """Singleton pointer to the current profile for single-operator installs."""

    __tablename__ = "active_profile"
    __table_args__ = (
        Index("ix_active_profile_profile_id", "profile_id"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    profile_id: Mapped[str] = mapped_column(
        ForeignKey("connection_profiles.id"),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
        nullable=False,
    )


class HealthRunRow(Base):
    """Aggregate health validation run for a stored profile."""

    __tablename__ = "health_runs"
    __table_args__ = (
        Index(
            "ix_health_runs_profile_checked_id",
            "profile_id",
            "checked_at",
            "id",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    profile_id: Mapped[str] = mapped_column(
        ForeignKey("connection_profiles.id"),
        nullable=False,
    )
    checked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        nullable=False,
    )
    overall_state: Mapped[str] = mapped_column(String(32), nullable=False)
    healthy_count: Mapped[int] = mapped_column(Integer, nullable=False)
    unhealthy_count: Mapped[int] = mapped_column(Integer, nullable=False)
    error_count: Mapped[int] = mapped_column(Integer, nullable=False)
    results: Mapped[list[HealthRunResultRow]] = relationship(
        back_populates="run",
        cascade="all, delete-orphan",
        order_by="HealthRunResultRow.service_order",
    )


class HealthRunResultRow(Base):
    """Service-level result row for a health validation run."""

    __tablename__ = "health_run_results"
    __table_args__ = (
        Index("ix_health_run_results_run_order", "run_id", "service_order"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    run_id: Mapped[str] = mapped_column(
        ForeignKey("health_runs.id"),
        nullable=False,
    )
    service_order: Mapped[int] = mapped_column(Integer, nullable=False)
    service_name: Mapped[str] = mapped_column(String(255), nullable=False)
    path: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    status_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    response_time_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    error_message: Mapped[str] = mapped_column(Text, nullable=False, default="")
    run: Mapped[HealthRunRow] = relationship(back_populates="results")
