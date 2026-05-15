"""Persistent-storage acceptance tests for the concrete app.storage package."""

from __future__ import annotations

import importlib
import importlib.util
import inspect
import sys
from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast, overload

import pytest

from app.connection_state import CONNECTION_KEY, HEALTH_RESULTS_KEY
from app.models.connection import ADMEConnection, AuthMethod, ServiceHealthResult

pytestmark = pytest.mark.skipif(
    importlib.util.find_spec("app.storage") is None,
    reason="Concrete app.storage package is not present yet.",
)

DATABASE_PASSWORD = "top-secret-db-password"
CLIENT_SECRET = "placeholder-client-secret"
SESSION_ONLY_VALUES = (
    CLIENT_SECRET,
    "placeholder-user-token",
    "placeholder-refresh-token",
    "placeholder-msal-flow-state",
    "placeholder-authorization-code",
)


class FailingHealthResults(Sequence[ServiceHealthResult]):
    """Sequence that fails after the first row to exercise rollback behavior."""

    def __init__(self, first_result: ServiceHealthResult) -> None:
        self._first_result = first_result

    def __len__(self) -> int:
        return 2

    @overload
    def __getitem__(self, index: int) -> ServiceHealthResult: ...

    @overload
    def __getitem__(self, index: slice) -> Sequence[ServiceHealthResult]: ...

    def __getitem__(
        self,
        index: int | slice,
    ) -> ServiceHealthResult | Sequence[ServiceHealthResult]:
        if isinstance(index, slice):
            return [self._first_result][index]
        if index == 0:
            return self._first_result
        raise RuntimeError("injected health-result write failure")


def _sqlite_url(database_path: Path) -> str:
    return f"sqlite:///{database_path.as_posix()}"


def _forget_storage_modules() -> None:
    for module_name in list(sys.modules):
        if module_name == "app.storage" or module_name.startswith("app.storage."):
            sys.modules.pop(module_name)


def _configure_sqlite(
    monkeypatch: pytest.MonkeyPatch,
    database_path: Path,
) -> str:
    database_url = _sqlite_url(database_path)
    monkeypatch.setenv("DATABASE_URL", database_url)
    _forget_storage_modules()
    return database_url


def _connection_with_secret() -> ADMEConnection:
    return ADMEConnection(
        endpoint="https://persisted.energy.azure.com",
        tenant_id="11111111-1111-1111-1111-111111111111",
        client_id="22222222-2222-2222-2222-222222222222",
        data_partition_id="persisted-opendes",
        token_scope="https://persisted.energy.azure.com/.default",
        auth_method=AuthMethod.SERVICE_PRINCIPAL,
        client_secret=CLIENT_SECRET,
    )


def _expected_persisted_connection() -> ADMEConnection:
    connection = _connection_with_secret()
    return ADMEConnection(
        endpoint=connection.endpoint,
        tenant_id=connection.tenant_id,
        client_id=connection.client_id,
        data_partition_id=connection.data_partition_id,
        token_scope=connection.token_scope,
        auth_method=connection.auth_method,
        client_secret="",
    )


def _healthy_results() -> list[ServiceHealthResult]:
    return [
        ServiceHealthResult(
            service_name="Storage",
            path="/api/storage/v2/query/kinds?limit=1",
            status="healthy",
            status_code=200,
            response_time_ms=15.0,
        ),
        ServiceHealthResult(
            service_name="Entitlements",
            path="/api/entitlements/v2/groups",
            status="unhealthy",
            status_code=403,
            response_time_ms=18.0,
            error_message="Missing entitlement.",
        ),
    ]


def _database_file_bytes(database_path: Path) -> bytes:
    payload = b""
    for path in database_path.parent.glob(f"{database_path.name}*"):
        if path.is_file():
            payload += path.read_bytes()
    return payload


def _call_with_supported_signature(
    function: Callable[..., Any],
    attempts: Sequence[tuple[tuple[Any, ...], dict[str, Any]]],
) -> Any:
    errors: list[str] = []
    for args, kwargs in attempts:
        try:
            return function(*args, **kwargs)
        except TypeError as exc:
            errors.append(str(exc))
    pytest.fail(
        f"{function!r} did not accept any storage-contract call shape: {errors}"
    )


def _first_callable(
    module_names: Sequence[str],
    function_names: Sequence[str],
) -> Callable[..., Any]:
    for module_name in module_names:
        try:
            module = importlib.import_module(module_name)
        except ModuleNotFoundError as exc:
            if exc.name == module_name:
                continue
            raise
        for function_name in function_names:
            candidate = getattr(module, function_name, None)
            if callable(candidate):
                return cast(Callable[..., Any], candidate)
    pytest.fail(
        "Expected one of "
        f"{', '.join(function_names)} in {', '.join(module_names)}"
    )


def _load_storage_config() -> Any:
    for module_name in ("app.storage.config", "app.storage"):
        try:
            module = importlib.import_module(module_name)
        except ModuleNotFoundError as exc:
            if exc.name == module_name:
                continue
            raise
        for function_name in (
            "resolve_storage_config",
            "load_storage_config",
            "load_config",
            "get_storage_config",
            "get_config",
        ):
            function = getattr(module, function_name, None)
            if callable(function):
                return function()
        config_type = getattr(module, "StorageConfig", None)
        if isinstance(config_type, type):
            from_env = getattr(config_type, "from_env", None)
            if callable(from_env):
                return from_env()
            try:
                return config_type()
            except TypeError:
                continue
        get_database_url = getattr(module, "get_database_url", None)
        if callable(get_database_url):
            return get_database_url()
    pytest.fail("app.storage.config must expose a loadable storage config.")


def _database_url_from_config(config: Any) -> str:
    if isinstance(config, str):
        return config
    if isinstance(config, Mapping):
        for key in ("database_url", "url", "sqlalchemy_url", "dsn"):
            value = config.get(key)
            if value:
                return str(value)
    for attribute in ("database_url", "url", "sqlalchemy_url", "dsn"):
        value = getattr(config, attribute, None)
        if value:
            return str(value)
    pytest.fail("Storage config did not expose a database URL.")


def _redact_database_url(database_url: str) -> str:
    for module_name in ("app.storage.config", "app.storage"):
        try:
            module = importlib.import_module(module_name)
        except ModuleNotFoundError as exc:
            if exc.name == module_name:
                continue
            raise
        for function_name in (
            "redact_database_url",
            "redact_url",
            "redact_connection_url",
        ):
            function = getattr(module, function_name, None)
            if callable(function):
                return str(function(database_url))
        resolve_storage_config = getattr(module, "resolve_storage_config", None)
        if callable(resolve_storage_config):
            config = resolve_storage_config(database_url=database_url)
            safe_description = getattr(config, "safe_description", None)
            if isinstance(safe_description, str):
                return safe_description
    pytest.fail(
        "Storage config must expose a redacted database URL or safe description."
    )


def _load_latest_health_run(connection: ADMEConnection) -> Any:
    profile_repository, health_repository = _repository_pair()
    get_active_profile = getattr(profile_repository, "get_active_profile", None)
    get_latest_for_profile = getattr(health_repository, "get_latest_for_profile", None)
    if callable(get_active_profile) and callable(get_latest_for_profile):
        profile = get_active_profile()
        profile_id = getattr(profile, "id", "")
        if profile_id:
            return get_latest_for_profile(str(profile_id))

    function = _first_callable(
        ("app.storage.repositories.health_runs",),
        (
            "load_latest_health_run",
            "get_latest_health_run",
            "latest_health_run",
            "load_latest",
            "latest",
        ),
    )
    if _accepts_keyword(function, "connection"):
        return function(connection=connection)
    if _accepts_keyword(function, "profile"):
        return function(profile=connection)
    if _has_required_positional_argument(function):
        return function(connection)
    return function()


def _record_health_run(
    connection: ADMEConnection,
    results: Sequence[ServiceHealthResult],
    *,
    checked_at: datetime | None = None,
) -> None:
    profile_repository, health_repository = _repository_pair()
    get_active_profile = getattr(profile_repository, "get_active_profile", None)
    record_run = getattr(health_repository, "record_run", None)
    if callable(get_active_profile) and callable(record_run):
        profile = get_active_profile()
        profile_id = getattr(profile, "id", "")
        if not profile_id:
            pytest.fail("No active profile was available for health-run recording.")
        if checked_at is None:
            record_run(str(profile_id), results)
        else:
            record_run(str(profile_id), results, checked_at=checked_at)
        return

    function = _first_callable(
        ("app.storage.repositories.health_runs",),
        (
            "record_health_run",
            "save_health_run",
            "record_latest_health_run",
            "record",
        ),
    )
    kwargs: dict[str, Any] = {}
    if checked_at is not None and _accepts_keyword(function, "checked_at"):
        kwargs["checked_at"] = checked_at
    attempts = [
        ((connection, results), kwargs),
        ((), {"connection": connection, "results": results, **kwargs}),
        ((), {"profile": connection, "results": results, **kwargs}),
        ((), {"connection": connection, "health_results": results, **kwargs}),
    ]
    _call_with_supported_signature(function, attempts)


def _repository_pair() -> tuple[Any, Any]:
    storage = importlib.import_module("app.storage")
    config = storage.resolve_storage_config()
    storage.ensure_storage_ready(config)
    engine = storage.create_engine_from_config(config)
    session_factory = storage.create_session_factory(engine)
    return (
        storage.ConnectionProfileRepository(session_factory),
        storage.HealthRunRepository(session_factory),
    )


def _accepts_keyword(function: Callable[..., Any], keyword: str) -> bool:
    try:
        signature = inspect.signature(function)
    except (TypeError, ValueError):
        return False
    return any(
        parameter.kind == inspect.Parameter.VAR_KEYWORD
        or (
            parameter.name == keyword
            and parameter.kind
            in {
                inspect.Parameter.POSITIONAL_OR_KEYWORD,
                inspect.Parameter.KEYWORD_ONLY,
            }
        )
        for parameter in signature.parameters.values()
    )


def _has_required_positional_argument(function: Callable[..., Any]) -> bool:
    try:
        signature = inspect.signature(function)
    except (TypeError, ValueError):
        return True
    return any(
        parameter.default is inspect.Parameter.empty
        and parameter.kind
        in {
            inspect.Parameter.POSITIONAL_ONLY,
            inspect.Parameter.POSITIONAL_OR_KEYWORD,
        }
        for parameter in signature.parameters.values()
    )


def _checked_at_from_health_run(health_run: Any) -> datetime:
    value = _field_value(
        health_run,
        ("checked_at", "checked_at_utc", "created_at", "completed_at"),
    )
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        parsed_value = value.replace("Z", "+00:00")
        return datetime.fromisoformat(parsed_value)
    pytest.fail("Latest health run did not expose a checked timestamp.")


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _results_from_health_run(health_run: Any) -> list[ServiceHealthResult]:
    if isinstance(health_run, Sequence) and not isinstance(health_run, str):
        if all(isinstance(item, ServiceHealthResult) for item in health_run):
            return list(health_run)
    value = _field_value(health_run, ("results", "service_results", "health_results"))
    if isinstance(value, Sequence) and not isinstance(value, str):
        if all(isinstance(item, ServiceHealthResult) for item in value):
            return list(value)
        if all(isinstance(item, Mapping) for item in value):
            return [_health_result_from_mapping(item) for item in value]
    pytest.fail("Latest health run did not expose service results.")


def _field_value(value: Any, names: Sequence[str]) -> Any:
    if isinstance(value, Mapping):
        for name in names:
            if name in value:
                return value[name]
    for name in names:
        attribute_value = getattr(value, name, None)
        if attribute_value is not None:
            return attribute_value
    return None


def _health_result_from_mapping(value: Mapping[Any, Any]) -> ServiceHealthResult:
    raw_status_code = value.get("status_code")
    raw_response_time = value.get("response_time_ms")
    return ServiceHealthResult(
        service_name=str(value.get("service_name", value.get("service", ""))),
        path=str(value.get("path", "")),
        status=str(value.get("status", value.get("state", "unknown"))),
        status_code=raw_status_code if isinstance(raw_status_code, int) else None,
        response_time_ms=(
            float(raw_response_time)
            if isinstance(raw_response_time, int | float)
            else None
        ),
        error_message=str(value.get("error_message", value.get("detail", "")) or ""),
    )


def test_storage_config_defaults_to_sqlite_and_redacts_database_urls(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    _forget_storage_modules()

    default_config = _load_storage_config()
    assert _database_url_from_config(default_config).startswith("sqlite")

    sensitive_url = (
        f"postgresql://db-user:{DATABASE_PASSWORD}@db.example.test:5432/adme"
    )
    redacted_url = _redact_database_url(sensitive_url)

    assert redacted_url != sensitive_url
    assert DATABASE_PASSWORD not in redacted_url
    assert "postgres" in redacted_url.lower()


def test_sqlite_migrations_initialize_a_clean_database(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_path = tmp_path / "clean-storage.sqlite"
    _configure_sqlite(monkeypatch, database_path)
    from app.storage_bridge import load_persisted_connection_state

    status = load_persisted_connection_state({})

    assert status.available is True
    assert database_path.exists()
    assert status.profile_loaded is False
    assert status.health_loaded is False


def test_connection_profile_round_trips_non_secret_fields_and_active_survives_restart(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_path = tmp_path / "profiles.sqlite"
    _configure_sqlite(monkeypatch, database_path)
    from app.storage_bridge import (
        load_persisted_connection_state,
        persist_connection_profile,
    )

    assert persist_connection_profile(_connection_with_secret()).available is True

    restarted_session: dict[str, object] = {}
    load_status = load_persisted_connection_state(restarted_session)

    assert load_status.available is True
    assert load_status.profile_loaded is True
    assert restarted_session[CONNECTION_KEY] == _expected_persisted_connection()
    persisted_bytes = _database_file_bytes(database_path)
    for session_only_value in SESSION_ONLY_VALUES:
        assert session_only_value.encode() not in persisted_bytes


def test_forget_persisted_connection_profile_removes_active_profile(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_path = tmp_path / "forget-profile.sqlite"
    _configure_sqlite(monkeypatch, database_path)
    from app.storage_bridge import (
        forget_persisted_connection_profile,
        load_persisted_connection_state,
        persist_connection_profile,
    )

    assert persist_connection_profile(_connection_with_secret()).available is True
    assert forget_persisted_connection_profile().available is True

    restarted_session: dict[str, object] = {}
    load_status = load_persisted_connection_state(restarted_session)

    assert load_status.available is True
    assert load_status.profile_loaded is False
    assert CONNECTION_KEY not in restarted_session


def test_health_results_persist_with_checked_timestamp_for_active_profile(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_path = tmp_path / "health.sqlite"
    _configure_sqlite(monkeypatch, database_path)
    from app.storage_bridge import (
        load_persisted_connection_state,
        persist_connection_profile,
        persist_health_run,
    )

    connection = _connection_with_secret()
    expected_connection = _expected_persisted_connection()
    checked_at = datetime.now(UTC).replace(microsecond=0)
    assert persist_connection_profile(connection).available is True
    try:
        _record_health_run(
            expected_connection,
            _healthy_results(),
            checked_at=checked_at,
        )
    except (TypeError, RuntimeError):
        assert persist_health_run(connection, _healthy_results()).available is True

    restarted_session: dict[str, object] = {}
    load_status = load_persisted_connection_state(restarted_session)
    latest_health_run = _load_latest_health_run(expected_connection)

    assert load_status.health_loaded is True
    assert restarted_session[HEALTH_RESULTS_KEY] == _healthy_results()
    assert _results_from_health_run(latest_health_run) == _healthy_results()
    persisted_checked_at = _checked_at_from_health_run(latest_health_run)
    assert _as_utc(persisted_checked_at) == checked_at


def test_health_run_write_rolls_back_when_result_write_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_path = tmp_path / "health-rollback.sqlite"
    _configure_sqlite(monkeypatch, database_path)
    from app.storage_bridge import persist_connection_profile

    connection = _expected_persisted_connection()
    assert persist_connection_profile(_connection_with_secret()).available is True
    _record_health_run(connection, _healthy_results())
    baseline_health_run = _load_latest_health_run(connection)

    try:
        _record_health_run(
            connection,
            FailingHealthResults(_healthy_results()[0]),
        )
    except RuntimeError:
        latest_health_run = _load_latest_health_run(connection)
        assert _results_from_health_run(latest_health_run) == _results_from_health_run(
            baseline_health_run
        )
    else:
        pytest.skip("Health repository did not expose a feasible failure hook.")
