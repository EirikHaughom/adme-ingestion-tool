"""Create storage tables.

Revision ID: 20260505_200000
Revises:
Create Date: 2026-05-05T20:00:00.287+02:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260505_200000"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create the initial non-secret storage schema."""
    op.create_table(
        "connection_profiles",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("display_name", sa.String(length=255), nullable=False),
        sa.Column("endpoint", sa.Text(), nullable=False),
        sa.Column("tenant_id", sa.String(length=255), nullable=False),
        sa.Column("client_id", sa.String(length=255), nullable=False),
        sa.Column("data_partition_id", sa.String(length=255), nullable=False),
        sa.Column("token_scope", sa.String(length=1024), nullable=False),
        sa.Column("auth_method", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "active_profile",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("profile_id", sa.String(length=64), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["profile_id"], ["connection_profiles.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "health_runs",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("profile_id", sa.String(length=64), nullable=False),
        sa.Column("checked_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("overall_state", sa.String(length=32), nullable=False),
        sa.Column("healthy_count", sa.Integer(), nullable=False),
        sa.Column("unhealthy_count", sa.Integer(), nullable=False),
        sa.Column("error_count", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["profile_id"], ["connection_profiles.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "health_run_results",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("run_id", sa.String(length=64), nullable=False),
        sa.Column("service_order", sa.Integer(), nullable=False),
        sa.Column("service_name", sa.String(length=255), nullable=False),
        sa.Column("path", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("status_code", sa.Integer(), nullable=True),
        sa.Column("response_time_ms", sa.Float(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(["run_id"], ["health_runs.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    _create_index(
        "ix_connection_profiles_deleted_display_id",
        "connection_profiles",
        ["deleted_at", "display_name", "id"],
    )
    _create_index("ix_active_profile_profile_id", "active_profile", ["profile_id"])
    _create_index(
        "ix_health_runs_profile_checked_id",
        "health_runs",
        ["profile_id", "checked_at", "id"],
    )
    _create_index(
        "ix_health_run_results_run_order",
        "health_run_results",
        ["run_id", "service_order"],
    )


def downgrade() -> None:
    """Drop the initial storage schema."""
    _drop_index("ix_health_run_results_run_order", "health_run_results")
    _drop_index("ix_health_runs_profile_checked_id", "health_runs")
    _drop_index("ix_active_profile_profile_id", "active_profile")
    _drop_index(
        "ix_connection_profiles_deleted_display_id",
        "connection_profiles",
    )
    op.drop_table("health_run_results")
    op.drop_table("health_runs")
    op.drop_table("active_profile")
    op.drop_table("connection_profiles")


def _create_index(name: str, table_name: str, columns: list[str]) -> None:
    if _dialect_name() == "postgresql":
        with op.get_context().autocommit_block():
            op.create_index(
                name,
                table_name,
                columns,
                postgresql_concurrently=True,
            )
        return
    op.create_index(name, table_name, columns)


def _drop_index(name: str, table_name: str) -> None:
    if _dialect_name() == "postgresql":
        with op.get_context().autocommit_block():
            op.drop_index(
                name,
                table_name=table_name,
                postgresql_concurrently=True,
            )
        return
    op.drop_index(name, table_name=table_name)


def _dialect_name() -> str:
    return op.get_bind().dialect.name
