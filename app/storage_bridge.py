"""UI-facing bridge to optional persistent storage repositories."""

from __future__ import annotations

import inspect
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from importlib import import_module
from types import ModuleType
from typing import Any, Literal, cast

from app.connection_state import (
    get_connection,
    save_connection,
    store_health_results,
)
from app.models.connection import (
    ADME_RESOURCE_SCOPE,
    ADMEConnection,
    AuthMethod,
    ServiceHealthResult,
)

StorageSeverity = Literal["none", "info", "warning", "error"]

STORAGE_UNAVAILABLE_MESSAGE = (
    "Persistent storage is not available. This Streamlit session remains usable, "
    "but saved settings and validation results will not survive an app restart."
)
STORAGE_OPERATION_FAILED_MESSAGE = (
    "Persistent storage could not be reached. This Streamlit session remains "
    "usable, but verify storage configuration before relying on saved settings."
)


@dataclass(frozen=True)
class StorageSyncStatus:
    """Operator-facing outcome for a storage sync attempt."""

    available: bool
    message: str = ""
    severity: StorageSeverity = "none"
    profile_loaded: bool = False
    health_loaded: bool = False


def connection_profile_without_secret(connection: ADMEConnection) -> ADMEConnection:
    """Return the persistable connection profile without session-only secrets."""
    return _without_client_secret(connection)


@dataclass(frozen=True)
class _StorageApi:
    initialize: Callable[..., object] | None
    load_profile: Callable[..., object]
    save_profile: Callable[..., object]
    load_latest_health_run: Callable[..., object] | None
    record_health_run: Callable[..., object] | None
    forget_profile: Callable[..., object] | None = None


def load_persisted_connection_state(session_state: Any) -> StorageSyncStatus:
    """Load the active saved profile and latest health run into Streamlit state."""
    try:
        api = _resolve_storage_api()
        _initialize_storage(api)
    except _StorageUnavailableError:
        return StorageSyncStatus(
            available=False,
            message=STORAGE_UNAVAILABLE_MESSAGE,
            severity="warning",
        )
    except Exception:  # noqa: BLE001 - keep storage details out of the UI
        return StorageSyncStatus(
            available=False,
            message=STORAGE_OPERATION_FAILED_MESSAGE,
            severity="error",
        )

    if get_connection(session_state) is not None:
        return StorageSyncStatus(available=True)

    try:
        loaded_profile = _connection_from_storage_value(api.load_profile())
        if loaded_profile is None:
            return StorageSyncStatus(available=True)

        save_connection(session_state, loaded_profile)
        loaded_results = _load_latest_results(api, loaded_profile)
        if loaded_results:
            store_health_results(session_state, loaded_results)

        loaded_message = (
            "Loaded saved connection settings and latest validation from "
            "persistent storage. Service-principal secrets load from the OS "
            "credential store; user sign-in still belongs to this Streamlit "
            "session."
            if loaded_results
            else "Loaded saved connection settings from persistent storage. "
            "Service-principal secrets load from the OS credential store; "
            "user sign-in still belongs to this Streamlit session."
        )
        return StorageSyncStatus(
            available=True,
            message=loaded_message,
            severity="info",
            profile_loaded=True,
            health_loaded=bool(loaded_results),
        )
    except Exception:  # noqa: BLE001 - keep storage details out of the UI
        return StorageSyncStatus(
            available=False,
            message=STORAGE_OPERATION_FAILED_MESSAGE,
            severity="error",
        )


def persist_connection_profile(connection: ADMEConnection) -> StorageSyncStatus:
    """Persist a non-secret connection profile and make it active."""
    try:
        api = _resolve_storage_api()
        _initialize_storage(api)
        _save_connection_profile(api.save_profile, _without_client_secret(connection))
    except _StorageUnavailableError:
        return StorageSyncStatus(
            available=False,
            message=STORAGE_UNAVAILABLE_MESSAGE,
            severity="warning",
        )
    except Exception:  # noqa: BLE001 - keep storage details out of the UI
        return StorageSyncStatus(
            available=False,
            message=STORAGE_OPERATION_FAILED_MESSAGE,
            severity="error",
        )

    return StorageSyncStatus(available=True)


def forget_persisted_connection_profile(
    profile_id: str | None = None,
) -> StorageSyncStatus:
    """Remove a saved profile from storage without touching session auth state."""
    try:
        api = _resolve_storage_api()
        _initialize_storage(api)
        if api.forget_profile is None:
            raise _StorageUnavailableError
        _forget_connection_profile(api.forget_profile, profile_id)
    except _StorageUnavailableError:
        return StorageSyncStatus(
            available=False,
            message=STORAGE_UNAVAILABLE_MESSAGE,
            severity="warning",
        )
    except Exception:  # noqa: BLE001 - keep storage details out of the UI
        return StorageSyncStatus(
            available=False,
            message=STORAGE_OPERATION_FAILED_MESSAGE,
            severity="error",
        )

    return StorageSyncStatus(available=True)


def persist_health_run(
    connection: ADMEConnection,
    results: Sequence[ServiceHealthResult],
) -> StorageSyncStatus:
    """Persist the latest completed health run for the active profile."""
    try:
        api = _resolve_storage_api()
        _initialize_storage(api)
        if api.record_health_run is None:
            raise _StorageUnavailableError
        _record_health_run(
            api.record_health_run,
            _without_client_secret(connection),
            list(results),
        )
    except _StorageUnavailableError:
        return StorageSyncStatus(
            available=False,
            message=STORAGE_UNAVAILABLE_MESSAGE,
            severity="warning",
        )
    except Exception:  # noqa: BLE001 - keep storage details out of the UI
        return StorageSyncStatus(
            available=False,
            message=STORAGE_OPERATION_FAILED_MESSAGE,
            severity="error",
        )

    return StorageSyncStatus(available=True)


class _StorageUnavailableError(Exception):
    """Raised when the storage package or expected repository functions are absent."""


def _resolve_storage_api() -> _StorageApi:
    storage_root = _optional_import("app.storage")
    if storage_root is None:
        raise _StorageUnavailableError

    repository_api = _repository_api_from_storage_root(storage_root)
    if repository_api is not None:
        return repository_api

    profile_repository = _optional_import(
        "app.storage.repositories.connection_profiles",
    )
    health_repository = _optional_import("app.storage.repositories.health_runs")
    if profile_repository is None:
        raise _StorageUnavailableError

    initialize = _first_callable(
        [
            storage_root,
            _optional_import("app.storage.engine"),
            _optional_import("app.storage.session"),
            _optional_import("app.storage.config"),
        ],
        (
            "initialize_storage",
            "ensure_storage_initialized",
            "ensure_storage_ready",
            "init_storage",
            "initialize",
        ),
    )
    load_profile = _first_callable(
        [profile_repository],
        (
            "load_active_connection_profile",
            "get_active_connection_profile",
            "load_active_profile",
            "get_active_profile",
            "load_active",
        ),
    )
    save_profile = _first_callable(
        [profile_repository],
        (
            "save_active_connection_profile",
            "save_connection_profile",
            "upsert_connection_profile",
            "save_profile",
            "save",
        ),
    )
    if load_profile is None or save_profile is None:
        raise _StorageUnavailableError

    load_latest_health_run = _first_callable(
        [health_repository] if health_repository is not None else [],
        (
            "load_latest_health_run",
            "get_latest_health_run",
            "latest_health_run",
            "load_latest",
            "latest",
        ),
    )
    record_health_run = _first_callable(
        [health_repository] if health_repository is not None else [],
        (
            "record_health_run",
            "save_health_run",
            "record_latest_health_run",
            "record",
        ),
    )
    delete_profile = _first_callable(
        [profile_repository],
        (
            "forget_connection_profile",
            "forget_profile",
            "delete_connection_profile",
            "delete_profile",
            "delete_connection",
            "delete",
        ),
    )
    clear_active_profile = _first_callable(
        [profile_repository],
        (
            "clear_active_connection_profile",
            "clear_active_profile",
            "clear_active_connection",
            "clear_active",
            "set_active_profile",
        ),
    )
    return _StorageApi(
        initialize=initialize,
        load_profile=load_profile,
        save_profile=save_profile,
        load_latest_health_run=load_latest_health_run,
        record_health_run=record_health_run,
        forget_profile=_build_forget_profile(
            load_profile,
            delete_profile,
            clear_active_profile,
        ),
    )


def _repository_api_from_storage_root(storage_root: ModuleType) -> _StorageApi | None:
    required_callables = (
        "resolve_storage_config",
        "ensure_storage_ready",
        "create_engine_from_config",
        "create_session_factory",
        "ConnectionProfileRepository",
        "HealthRunRepository",
    )
    if not all(
        callable(getattr(storage_root, name, None)) for name in required_callables
    ):
        return None

    connection_profile_type = getattr(storage_root, "ConnectionProfile", None)
    from_connection = getattr(connection_profile_type, "from_connection", None)
    if not callable(from_connection):
        return None

    resolve_storage_config = cast(
        Callable[[], object],
        getattr(storage_root, "resolve_storage_config"),
    )
    ensure_storage_ready = cast(
        Callable[[object], None],
        getattr(storage_root, "ensure_storage_ready"),
    )
    create_engine_from_config = cast(
        Callable[[object], object],
        getattr(storage_root, "create_engine_from_config"),
    )
    create_session_factory = cast(
        Callable[[object], object],
        getattr(storage_root, "create_session_factory"),
    )
    profile_repository_type = cast(
        Callable[[object], object],
        getattr(storage_root, "ConnectionProfileRepository"),
    )
    health_repository_type = cast(
        Callable[[object], object],
        getattr(storage_root, "HealthRunRepository"),
    )
    build_profile = cast(
        Callable[..., object],
        from_connection,
    )

    def initialize_repositories() -> tuple[object, object, object]:
        config = resolve_storage_config()
        ensure_storage_ready(config)
        engine = create_engine_from_config(config)
        session_factory = create_session_factory(engine)
        return (
            engine,
            profile_repository_type(session_factory),
            health_repository_type(session_factory),
        )

    def load_profile() -> object:
        engine, profile_repository, _health_repository = initialize_repositories()
        try:
            return _get_active_profile(profile_repository)
        finally:
            _dispose_storage_engine(engine)

    def save_profile(connection: ADMEConnection) -> object:
        engine, profile_repository, _health_repository = initialize_repositories()
        try:
            return _save_profile_with_repository(
                profile_repository,
                build_profile,
                connection,
            )
        finally:
            _dispose_storage_engine(engine)

    def load_latest_health_run(connection: ADMEConnection) -> object:
        engine, profile_repository, health_repository = initialize_repositories()
        try:
            active_profile = _get_active_profile(profile_repository)
            active_profile_id = getattr(active_profile, "id", "")
            if not active_profile_id:
                return None
            get_latest_for_profile = cast(
                Callable[[str], object],
                getattr(health_repository, "get_latest_for_profile"),
            )
            return get_latest_for_profile(str(active_profile_id))
        finally:
            _dispose_storage_engine(engine)

    def record_health_run(
        connection: ADMEConnection,
        results: list[ServiceHealthResult],
    ) -> object:
        engine, profile_repository, health_repository = initialize_repositories()
        try:
            saved_profile = _save_profile_with_repository(
                profile_repository,
                build_profile,
                connection,
            )
            saved_profile_id = getattr(saved_profile, "id", "")
            if not saved_profile_id:
                raise ValueError("Saved profile did not return an id.")
            repository_record_run = cast(
                Callable[[str, list[ServiceHealthResult]], object],
                getattr(health_repository, "record_run"),
            )
            return repository_record_run(str(saved_profile_id), results)
        finally:
            _dispose_storage_engine(engine)

    def forget_profile(profile_id: str | None = None) -> bool:
        engine, profile_repository, _health_repository = initialize_repositories()
        try:
            target_profile_id = profile_id
            if target_profile_id is None:
                active_profile = _get_active_profile(profile_repository)
                target_profile_id = _profile_id_from_storage_value(active_profile)
            if not target_profile_id:
                _clear_active_profile_pointer(profile_repository)
                return False
            deleted = _delete_profile_with_repository(
                profile_repository,
                target_profile_id,
            )
            _clear_active_profile_pointer(profile_repository)
            return deleted
        finally:
            _dispose_storage_engine(engine)

    return _StorageApi(
        initialize=None,
        load_profile=load_profile,
        save_profile=save_profile,
        load_latest_health_run=load_latest_health_run,
        record_health_run=record_health_run,
        forget_profile=forget_profile,
    )


def _get_active_profile(profile_repository: object) -> object | None:
    get_active_profile = cast(
        Callable[[], object | None],
        getattr(profile_repository, "get_active_profile"),
    )
    return get_active_profile()


def _save_profile_with_repository(
    profile_repository: object,
    build_profile: Callable[..., object],
    connection: ADMEConnection,
) -> object:
    active_profile = _get_active_profile(profile_repository)
    active_profile_id = getattr(active_profile, "id", "")
    profile = build_profile(
        display_name=_display_name_for_connection(connection),
        connection=connection,
        profile_id=str(active_profile_id or ""),
    )
    repository_save_profile = cast(
        Callable[[object], object],
        getattr(profile_repository, "save_profile"),
    )
    set_active_profile = cast(
        Callable[[str], object],
        getattr(profile_repository, "set_active_profile"),
    )
    saved_profile = repository_save_profile(profile)
    saved_profile_id = getattr(saved_profile, "id", "")
    if saved_profile_id:
        set_active_profile(str(saved_profile_id))
    return saved_profile


def _delete_profile_with_repository(
    profile_repository: object,
    profile_id: str,
) -> bool:
    delete_profile = cast(
        Callable[[str], bool],
        getattr(profile_repository, "delete_profile"),
    )
    return bool(delete_profile(profile_id))


def _clear_active_profile_pointer(profile_repository: object) -> None:
    set_active_profile = cast(
        Callable[[str | None], object],
        getattr(profile_repository, "set_active_profile"),
    )
    set_active_profile(None)


def _dispose_storage_engine(engine: object) -> None:
    dispose = getattr(engine, "dispose", None)
    if callable(dispose):
        cast(Callable[[], None], dispose)()


def _display_name_for_connection(connection: ADMEConnection) -> str:
    return connection.data_partition_id.strip() or connection.endpoint.strip()


def _optional_import(module_name: str) -> ModuleType | None:
    try:
        return import_module(module_name)
    except ModuleNotFoundError:
        return None


def _first_callable(
    modules: Sequence[ModuleType | None],
    names: Sequence[str],
) -> Callable[..., object] | None:
    for module in modules:
        if module is None:
            continue
        for name in names:
            candidate = getattr(module, name, None)
            if callable(candidate):
                return cast(Callable[..., object], candidate)
    return None


def _initialize_storage(api: _StorageApi) -> None:
    if api.initialize is not None:
        api.initialize()


def _save_connection_profile(
    save_profile: Callable[..., object],
    connection: ADMEConnection,
) -> None:
    kwargs: dict[str, object] = {}
    for name in ("set_active", "active", "make_active", "is_active"):
        if _accepts_keyword(save_profile, name):
            kwargs[name] = True
            break

    if _accepts_keyword(save_profile, "connection"):
        save_profile(connection=connection, **kwargs)
        return
    if _accepts_keyword(save_profile, "profile"):
        save_profile(profile=connection, **kwargs)
        return
    save_profile(connection, **kwargs)


def _record_health_run(
    record_health_run: Callable[..., object],
    connection: ADMEConnection,
    results: list[ServiceHealthResult],
) -> None:
    kwargs: dict[str, object] = {}
    if _accepts_keyword(record_health_run, "connection"):
        kwargs["connection"] = connection
    elif _accepts_keyword(record_health_run, "profile"):
        kwargs["profile"] = connection

    if _accepts_keyword(record_health_run, "results"):
        kwargs["results"] = results
    elif _accepts_keyword(record_health_run, "health_results"):
        kwargs["health_results"] = results

    if kwargs:
        record_health_run(**kwargs)
        return
    record_health_run(connection, results)


def _forget_connection_profile(
    forget_profile: Callable[..., object],
    profile_id: str | None,
) -> None:
    if _accepts_keyword(forget_profile, "profile_id"):
        forget_profile(profile_id=profile_id)
        return
    if profile_id is not None and _has_required_positional_argument(forget_profile):
        forget_profile(profile_id)
        return
    forget_profile()


def _build_forget_profile(
    load_profile: Callable[..., object],
    delete_profile: Callable[..., object] | None,
    clear_active_profile: Callable[..., object] | None,
) -> Callable[[str | None], object] | None:
    if delete_profile is None and clear_active_profile is None:
        return None

    def forget_profile(profile_id: str | None = None) -> object:
        target_profile_id = profile_id
        if target_profile_id is None and delete_profile is not None:
            target_profile_id = _profile_id_from_storage_value(load_profile())
        if target_profile_id and delete_profile is not None:
            _delete_connection_profile(delete_profile, target_profile_id)
        elif delete_profile is not None and not _has_required_positional_argument(
            delete_profile,
        ):
            delete_profile()
        if clear_active_profile is not None:
            _clear_active_connection_profile(clear_active_profile)
        return None

    return forget_profile


def _delete_connection_profile(
    delete_profile: Callable[..., object],
    profile_id: str,
) -> None:
    for keyword in ("profile_id", "connection_id", "id", "name"):
        if _accepts_keyword(delete_profile, keyword):
            delete_profile(**{keyword: profile_id})
            return
    if _has_required_positional_argument(delete_profile):
        delete_profile(profile_id)
        return
    delete_profile()


def _clear_active_connection_profile(
    clear_active_profile: Callable[..., object],
) -> None:
    if _accepts_keyword(clear_active_profile, "profile_id"):
        clear_active_profile(profile_id=None)
        return
    if _has_required_positional_argument(clear_active_profile):
        clear_active_profile(None)
        return
    clear_active_profile()


def _load_latest_results(
    api: _StorageApi,
    connection: ADMEConnection,
) -> list[ServiceHealthResult]:
    if api.load_latest_health_run is None:
        return []

    load_latest_health_run = api.load_latest_health_run
    if _accepts_keyword(load_latest_health_run, "connection"):
        raw_result = load_latest_health_run(connection=connection)
    elif _accepts_keyword(load_latest_health_run, "profile"):
        raw_result = load_latest_health_run(profile=connection)
    elif _has_required_positional_argument(load_latest_health_run):
        raw_result = load_latest_health_run(connection)
    else:
        raw_result = load_latest_health_run()
    return _health_results_from_storage_value(raw_result)


def _accepts_keyword(function: Callable[..., object], keyword: str) -> bool:
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


def _has_required_positional_argument(function: Callable[..., object]) -> bool:
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


def _connection_from_storage_value(value: object) -> ADMEConnection | None:
    if value is None:
        return None
    if isinstance(value, ADMEConnection):
        return _without_client_secret(value)
    for attribute in ("connection", "profile", "connection_profile"):
        nested_value = getattr(value, attribute, None)
        if isinstance(nested_value, ADMEConnection):
            return _without_client_secret(nested_value)
    if isinstance(value, dict):
        return _connection_from_mapping(value)
    return None


def _profile_id_from_storage_value(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, dict):
        for key in ("id", "profile_id", "name"):
            profile_id = value.get(key)
            if isinstance(profile_id, str) and profile_id.strip():
                return profile_id.strip()
    for attribute in ("id", "profile_id", "name"):
        profile_id = getattr(value, attribute, None)
        if isinstance(profile_id, str) and profile_id.strip():
            return profile_id.strip()
    return ""


def _connection_from_mapping(value: dict[object, object]) -> ADMEConnection | None:
    required_fields = ("endpoint", "tenant_id", "client_id", "data_partition_id")
    if not all(isinstance(value.get(field), str) for field in required_fields):
        return None

    raw_auth_method = value.get("auth_method", AuthMethod.USER_IMPERSONATION.value)
    try:
        auth_method = AuthMethod(str(raw_auth_method))
    except ValueError:
        auth_method = AuthMethod.USER_IMPERSONATION

    token_scope = value.get("token_scope", ADME_RESOURCE_SCOPE)
    return ADMEConnection(
        endpoint=str(value["endpoint"]),
        tenant_id=str(value["tenant_id"]),
        client_id=str(value["client_id"]),
        data_partition_id=str(value["data_partition_id"]),
        token_scope=(
            str(token_scope) if token_scope is not None else ADME_RESOURCE_SCOPE
        ),
        auth_method=auth_method,
        client_secret="",
    )


def _health_results_from_storage_value(value: object) -> list[ServiceHealthResult]:
    if value is None:
        return []
    results = _health_result_list(value)
    if results is not None:
        return results
    for attribute in ("results", "service_results", "health_results"):
        nested_value = getattr(value, attribute, None)
        results = _health_result_list(nested_value)
        if results is not None:
            return results
    if isinstance(value, dict):
        for key in ("results", "service_results", "health_results"):
            nested_value = value.get(key)
            results = _health_result_list(nested_value)
            if results is not None:
                return results
            mappings = _health_mapping_list(nested_value)
            if mappings is not None:
                return [_health_result_from_mapping(item) for item in mappings]
    mappings = _health_mapping_list(value)
    if mappings is not None:
        return [_health_result_from_mapping(item) for item in mappings]
    return []


def _health_result_list(value: object) -> list[ServiceHealthResult] | None:
    if not isinstance(value, Sequence) or isinstance(value, str):
        return None
    results: list[ServiceHealthResult] = []
    for item in value:
        if not isinstance(item, ServiceHealthResult):
            return None
        results.append(item)
    return results


def _health_mapping_list(value: object) -> list[dict[object, object]] | None:
    if not isinstance(value, Sequence) or isinstance(value, str):
        return None
    mappings: list[dict[object, object]] = []
    for item in value:
        if not isinstance(item, dict):
            return None
        mappings.append(item)
    return mappings


def _health_result_from_mapping(value: dict[object, object]) -> ServiceHealthResult:
    status_code = value.get("status_code")
    response_time_ms = value.get("response_time_ms")
    return ServiceHealthResult(
        service_name=str(value.get("service_name", value.get("service", ""))),
        path=str(value.get("path", "")),
        status=str(value.get("status", value.get("state", "unknown"))),
        status_code=int(status_code) if isinstance(status_code, int) else None,
        response_time_ms=(
            float(response_time_ms)
            if isinstance(response_time_ms, (int, float))
            else None
        ),
        error_message=str(value.get("error_message", value.get("detail", "")) or ""),
    )


def _without_client_secret(connection: ADMEConnection) -> ADMEConnection:
    return ADMEConnection(
        endpoint=connection.endpoint,
        tenant_id=connection.tenant_id,
        client_id=connection.client_id,
        data_partition_id=connection.data_partition_id,
        token_scope=connection.token_scope,
        auth_method=connection.auth_method,
        client_secret="",
    )
