"""Repository for non-secret ADME connection profiles."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import delete, select
from sqlalchemy.orm import Session, sessionmaker

from app.models.connection import ADMEConnection, AuthMethod
from app.storage.models import ActiveProfileRow, ConnectionProfileRow, utc_now
from app.storage.session import session_scope

ACTIVE_PROFILE_ID = "active"


@dataclass(frozen=True)
class ConnectionProfile:
    """Domain representation of a persisted, non-secret ADME profile."""

    display_name: str
    connection: ADMEConnection
    id: str = ""
    created_at: datetime | None = None
    updated_at: datetime | None = None
    deleted_at: datetime | None = None

    @classmethod
    def from_connection(
        cls,
        *,
        display_name: str,
        connection: ADMEConnection,
        profile_id: str = "",
    ) -> ConnectionProfile:
        """Build a profile from the shared ADME connection dataclass."""
        return cls(
            id=profile_id,
            display_name=display_name,
            connection=connection,
        )


class ConnectionProfileRepository:
    """Transaction-scoped repository for connection profile persistence."""

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def list_profiles(self) -> list[ConnectionProfile]:
        """Return non-deleted profiles in deterministic display order."""
        with session_scope(self._session_factory) as session:
            rows = session.scalars(
                select(ConnectionProfileRow)
                .where(ConnectionProfileRow.deleted_at.is_(None))
                .order_by(ConnectionProfileRow.display_name, ConnectionProfileRow.id)
            ).all()
            return [_profile_from_row(row) for row in rows]

    def get_profile(self, profile_id: str) -> ConnectionProfile | None:
        """Return a non-deleted profile by id."""
        with session_scope(self._session_factory) as session:
            row = session.get(ConnectionProfileRow, profile_id)
            if row is None or row.deleted_at is not None:
                return None
            return _profile_from_row(row)

    def save_profile(self, profile: ConnectionProfile) -> ConnectionProfile:
        """Insert or update a profile, rejecting secret-bearing connections."""
        _validate_profile(profile)
        now = utc_now()
        profile_id = profile.id or uuid4().hex

        with session_scope(self._session_factory) as session:
            row = session.get(ConnectionProfileRow, profile_id)
            if row is None:
                row = ConnectionProfileRow(
                    id=profile_id,
                    display_name=profile.display_name.strip(),
                    endpoint=profile.connection.endpoint.strip(),
                    tenant_id=profile.connection.tenant_id.strip(),
                    client_id=profile.connection.client_id.strip(),
                    data_partition_id=profile.connection.data_partition_id.strip(),
                    token_scope=profile.connection.scope,
                    auth_method=AuthMethod(profile.connection.auth_method).value,
                    created_at=_normalize_datetime(profile.created_at) or now,
                    updated_at=now,
                    deleted_at=None,
                )
                session.add(row)
            else:
                row.display_name = profile.display_name.strip()
                row.endpoint = profile.connection.endpoint.strip()
                row.tenant_id = profile.connection.tenant_id.strip()
                row.client_id = profile.connection.client_id.strip()
                row.data_partition_id = profile.connection.data_partition_id.strip()
                row.token_scope = profile.connection.scope
                row.auth_method = AuthMethod(profile.connection.auth_method).value
                row.updated_at = now
                row.deleted_at = None

            session.flush()
            return _profile_from_row(row)

    def delete_profile(self, profile_id: str) -> bool:
        """Soft-delete a profile and clear it if it was active."""
        with session_scope(self._session_factory) as session:
            row = session.get(ConnectionProfileRow, profile_id)
            if row is None or row.deleted_at is not None:
                return False

            now = utc_now()
            row.deleted_at = now
            row.updated_at = now
            session.execute(
                delete(ActiveProfileRow).where(
                    ActiveProfileRow.profile_id == profile_id
                )
            )
            return True

    def get_active_profile(self) -> ConnectionProfile | None:
        """Return the singleton active profile if it still exists."""
        with session_scope(self._session_factory) as session:
            active = session.get(ActiveProfileRow, ACTIVE_PROFILE_ID)
            if active is None:
                return None

            row = session.get(ConnectionProfileRow, active.profile_id)
            if row is None or row.deleted_at is not None:
                return None
            return _profile_from_row(row)

    def set_active_profile(self, profile_id: str | None) -> ConnectionProfile | None:
        """Set or clear the active profile pointer."""
        with session_scope(self._session_factory) as session:
            if profile_id is None:
                session.execute(
                    delete(ActiveProfileRow).where(
                        ActiveProfileRow.id == ACTIVE_PROFILE_ID
                    )
                )
                return None

            row = session.get(ConnectionProfileRow, profile_id)
            if row is None or row.deleted_at is not None:
                raise ValueError("Active profile must reference an existing profile.")

            active = session.get(ActiveProfileRow, ACTIVE_PROFILE_ID)
            if active is None:
                active = ActiveProfileRow(
                    id=ACTIVE_PROFILE_ID,
                    profile_id=profile_id,
                    updated_at=utc_now(),
                )
                session.add(active)
            else:
                active.profile_id = profile_id
                active.updated_at = utc_now()

            session.flush()
            return _profile_from_row(row)


def _validate_profile(profile: ConnectionProfile) -> None:
    display_name = profile.display_name.strip()
    connection = profile.connection
    if not display_name:
        raise ValueError("Connection profile display name is required.")
    if connection.client_secret:
        raise ValueError(
            "Connection profiles cannot persist client_secret. Store service "
            "principal secrets outside the storage boundary."
        )
    if not (
        connection.endpoint.strip()
        and connection.tenant_id.strip()
        and connection.client_id.strip()
        and connection.data_partition_id.strip()
    ):
        raise ValueError(
            "Connection profile requires endpoint, tenant ID, client ID, and "
            "data partition ID."
        )
    AuthMethod(connection.auth_method)


def _profile_from_row(row: ConnectionProfileRow) -> ConnectionProfile:
    return ConnectionProfile(
        id=row.id,
        display_name=row.display_name,
        connection=ADMEConnection(
            endpoint=row.endpoint,
            tenant_id=row.tenant_id,
            client_id=row.client_id,
            data_partition_id=row.data_partition_id,
            token_scope=row.token_scope,
            auth_method=AuthMethod(row.auth_method),
            client_secret="",
        ),
        created_at=_normalize_datetime(row.created_at),
        updated_at=_normalize_datetime(row.updated_at),
        deleted_at=_normalize_datetime(row.deleted_at),
    )


def _normalize_datetime(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
