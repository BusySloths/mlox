"""Facade over the MLOX application use-cases."""

from __future__ import annotations

import os
from typing import Dict, Optional, Tuple

from mlox.application.result import OperationResult
from mlox.application.use_cases import models, project, servers, services
from mlox.config import (
    get_stacks_path,
    load_all_server_configs,
    load_all_service_configs,
    load_config,
    load_service_config_by_id,
)
from mlox.session import MloxSession
from mlox.utils import save_to_json

DEFAULT_MLSERVER_TEMPLATE_ID = "mlflow-mlserver-2.22.0-docker"


class _SessionCache:
    """Basic in-memory cache for loaded :class:`MloxSession` objects."""

    def __init__(self) -> None:
        self._sessions: Dict[Tuple[str, str], MloxSession] = {}

    def get(self, project: str, password: str) -> Optional[MloxSession]:
        return self._sessions.get((project, password))

    def set(self, project: str, password: str, session: MloxSession) -> None:
        self._sessions[(project, password)] = session

    def invalidate(self, project: Optional[str] = None) -> None:
        if project is None:
            self._sessions.clear()
            return

        keys_to_remove = [key for key in self._sessions if key[0] == project]
        for key in keys_to_remove:
            self._sessions.pop(key, None)


_SESSION_CACHE = _SessionCache()


def _load_session(
    project: str,
    password: str,
    *,
    refresh: bool = False,
) -> OperationResult:
    """Load a session, optionally reloading the cache."""

    if not refresh:
        cached = _SESSION_CACHE.get(project, password)
        if cached:
            if cached.secrets and not cached.secrets.is_working():
                _SESSION_CACHE.invalidate(project)
            else:
                return OperationResult(True, 0, "Session loaded from cache.", cached)

    try:
        session = MloxSession(project_name=project, password=password)
    except SystemExit:
        raise
    except Exception as exc:
        return OperationResult(False, 1, f"Failed to load session: {exc}")

    if session.secrets and not session.secrets.is_working():
        _SESSION_CACHE.invalidate(project)
        return OperationResult(
            False, 2, "Secret manager for the project is not working."
        )

    _SESSION_CACHE.set(project, password, session)
    return OperationResult(True, 0, "Session loaded.", session)


def _load_config_from_path(path: str):
    stacks = get_stacks_path()
    service_dir, candidate = os.path.split(path)
    return load_config(stacks, service_dir, candidate)


def create_project(name: str, password: str) -> OperationResult:
    return project.create_project(_load_session, name, password)


def list_servers(project: str, password: str) -> OperationResult:
    return servers.list_servers(_load_session, project, password)


def add_server(
    project: str,
    password: str,
    *,
    template_path: str,
    ip: str,
    port: int,
    root_user: str,
    root_password: str,
    extra_params: Optional[Dict[str, str]] = None,
) -> OperationResult:
    return servers.add_server(
        _load_session,
        _load_config_from_path,
        project,
        password,
        template_path=template_path,
        ip=ip,
        port=port,
        root_user=root_user,
        root_password=root_password,
        extra_params=extra_params,
    )


def setup_server(project: str, password: str, *, ip: str) -> OperationResult:
    return servers.setup_server(_load_session, project, password, ip=ip)


def teardown_server(project: str, password: str, *, ip: str) -> OperationResult:
    return servers.teardown_server(_load_session, project, password, ip=ip)


def save_server_key(
    project: str,
    password: str,
    *,
    ip: str,
    output_path: str,
) -> OperationResult:
    return servers.save_server_key(
        _load_session,
        save_to_json,
        project,
        password,
        ip=ip,
        output_path=output_path,
    )


def list_services(project: str, password: str) -> OperationResult:
    return services.list_services(_load_session, project, password)


def add_service(
    project: str,
    password: str,
    *,
    server_ip: str,
    template_id: str,
    params: Optional[Dict[str, str]] = None,
) -> OperationResult:
    return services.add_service(
        _load_session,
        load_service_config_by_id,
        project,
        password,
        server_ip=server_ip,
        template_id=template_id,
        params=params,
    )


def setup_service(project: str, password: str, *, name: str) -> OperationResult:
    return services.setup_service(_load_session, project, password, name=name)


def teardown_service(project: str, password: str, *, name: str) -> OperationResult:
    return services.teardown_service(_load_session, project, password, name=name)


def service_logs(
    project: str,
    password: str,
    *,
    name: str,
    label: Optional[str] = None,
    tail: int = 200,
) -> OperationResult:
    return services.service_logs(
        _load_session,
        project,
        password,
        name=name,
        label=label,
        tail=tail,
    )


def list_models(
    project: str,
    password: str,
    *,
    registry_name: Optional[str] = None,
) -> OperationResult:
    return models.list_models(
        _load_session,
        project,
        password,
        registry_name=registry_name,
    )


def deploy_model(
    project: str,
    password: str,
    *,
    registry_name: Optional[str],
    model_name: str,
    model_version: str,
    server_ip: str,
    template_id: str = DEFAULT_MLSERVER_TEMPLATE_ID,
) -> OperationResult:
    return models.deploy_model(
        _load_session,
        add_service,
        setup_service,
        project,
        password,
        registry_name=registry_name,
        model_name=model_name,
        model_version=model_version,
        server_ip=server_ip,
        template_id=template_id,
    )


def list_server_configs() -> OperationResult:
    return servers.list_server_configs(load_all_server_configs)


def list_service_configs() -> OperationResult:
    return services.list_service_configs(load_all_service_configs)


def invalidate_session_cache(project: Optional[str] = None) -> None:
    """Clear cached sessions for a project or entirely."""

    _SESSION_CACHE.invalidate(project)
