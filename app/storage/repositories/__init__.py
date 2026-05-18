"""Repository contracts exposed by the storage boundary."""

from app.storage.repositories.connection_profiles import (
    ConnectionProfile,
    ConnectionProfileRepository,
)
from app.storage.repositories.health_runs import HealthRunRepository, HealthRunSummary

__all__ = [
    "ConnectionProfile",
    "ConnectionProfileRepository",
    "HealthRunRepository",
    "HealthRunSummary",
]
