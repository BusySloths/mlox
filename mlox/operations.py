"""Core operations for interacting with MLOX projects.

This module centralises the business logic used by the different user
interfaces (CLI, TUI, web UI, ...). Each operation returns an
``OperationResult`` which carries a success flag, an error code, a
human-readable message and optional payload data.

The functions are designed to be side-effect free outside of their
intended purpose and expose a small cache to avoid repeated session
initialisation for the same project credentials.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from mlox.config import (
    get_stacks_path,
    load_all_server_configs,
    load_all_service_configs,
    load_config,
    load_service_config_by_id,
)
from mlox.session import MloxSession
from mlox.utils import dataclass_to_dict, save_to_json


@dataclass
class OperationResult:
    """Container describing the outcome of an operation."""

    success: bool
    code: int
    message: str
    data: Any | None = None

    def __bool__(self) -> bool:  # pragma: no cover - syntactic sugar
        return self.success


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


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


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
        return OperationResult(False, 2, "Secret manager for the project is not working.")

    _SESSION_CACHE.set(project, password, session)
    return OperationResult(True, 0, "Session loaded.", session)


def _load_config_from_path(path: str):
    stacks = get_stacks_path()
    service_dir, candidate = os.path.split(path)
    return load_config(stacks, service_dir, candidate)


# ---------------------------------------------------------------------------
# Project operations
# ---------------------------------------------------------------------------


def create_project(name: str, password: str) -> OperationResult:
    """Create or load a project by initialising a session."""

    result = _load_session(name, password, refresh=True)
    if not result.success:
        return result
    session = result.data
    assert isinstance(session, MloxSession)
    return OperationResult(True, 0, f"Created project '{name}'.", {"session": session})


# ---------------------------------------------------------------------------
# Server operations
# ---------------------------------------------------------------------------


def list_servers(project: str, password: str) -> OperationResult:
    result = _load_session(project, password)
    if not result.success:
        return result
    session = result.data
    assert isinstance(session, MloxSession)
    servers: List[Dict[str, Any]] = []
    for bundle in session.infra.bundles:
        servers.append(
            {
                "ip": bundle.server.ip,
                "state": getattr(bundle.server, "state", "unknown"),
                "service_count": len(bundle.services),
            }
        )
    message = "No servers found." if not servers else "Servers retrieved successfully."
    return OperationResult(True, 0, message, {"servers": servers})


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
    result = _load_session(project, password)
    if not result.success:
        return result
    session = result.data
    assert isinstance(session, MloxSession)

    config = _load_config_from_path(template_path)
    if config is None:
        return OperationResult(False, 3, "Server template not found.")

    params = {
        "${MLOX_IP}": ip,
        "${MLOX_PORT}": str(port),
        "${MLOX_ROOT}": root_user,
        "${MLOX_ROOT_PW}": root_password,
    }
    if extra_params:
        params.update(extra_params)

    bundle = session.infra.add_server(config=config, params=params)
    if not bundle:
        return OperationResult(False, 4, "Failed to add server to the project infrastructure.")

    session.save_infrastructure()
    return OperationResult(True, 0, f"Added server {ip}.", {"bundle": bundle})


def setup_server(project: str, password: str, *, ip: str) -> OperationResult:
    result = _load_session(project, password)
    if not result.success:
        return result
    session = result.data
    assert isinstance(session, MloxSession)

    bundle = session.infra.get_bundle_by_ip(ip)
    if not bundle:
        return OperationResult(False, 5, "Server not found in infrastructure.")

    bundle.server.setup()
    session.save_infrastructure()
    return OperationResult(True, 0, f"Server {ip} set up.")


def teardown_server(project: str, password: str, *, ip: str) -> OperationResult:
    result = _load_session(project, password)
    if not result.success:
        return result
    session = result.data
    assert isinstance(session, MloxSession)

    bundle = session.infra.get_bundle_by_ip(ip)
    if not bundle:
        return OperationResult(False, 5, "Server not found in infrastructure.")

    bundle.server.teardown()
    session.infra.remove_bundle(bundle)
    session.save_infrastructure()
    return OperationResult(True, 0, f"Server {ip} removed from infrastructure.")


def save_server_key(
    project: str,
    password: str,
    *,
    ip: str,
    output_path: str,
) -> OperationResult:
    result = _load_session(project, password)
    if not result.success:
        return result
    session = result.data
    assert isinstance(session, MloxSession)

    bundle = session.infra.get_bundle_by_ip(ip)
    if not bundle:
        return OperationResult(False, 5, "Server not found in infrastructure.")

    server_dict = dataclass_to_dict(bundle.server)
    save_to_json(server_dict, output_path, password, True)
    return OperationResult(True, 0, f"Saved key for {ip} to {output_path}.")


# ---------------------------------------------------------------------------
# Service operations
# ---------------------------------------------------------------------------


def list_services(project: str, password: str) -> OperationResult:
    result = _load_session(project, password)
    if not result.success:
        return result
    session = result.data
    assert isinstance(session, MloxSession)

    services: List[Dict[str, Any]] = []
    for bundle in session.infra.bundles:
        for svc in bundle.services:
            services.append(
                {
                    "name": svc.name,
                    "service_config_id": getattr(svc, "service_config_id", "unknown"),
                    "server_ip": bundle.server.ip,
                }
            )
    message = "No services found." if not services else "Services retrieved successfully."
    return OperationResult(True, 0, message, {"services": services})


def add_service(
    project: str,
    password: str,
    *,
    server_ip: str,
    template_id: str,
    params: Optional[Dict[str, str]] = None,
) -> OperationResult:
    result = _load_session(project, password)
    if not result.success:
        return result
    session = result.data
    assert isinstance(session, MloxSession)

    config = load_service_config_by_id(template_id)
    if not config:
        return OperationResult(False, 6, "Service template not found.")

    bundle = session.infra.add_service(server_ip, config, params or {})
    if not bundle:
        return OperationResult(False, 7, "Failed to add service to server.")

    session.save_infrastructure()
    svc = bundle.services[-1]
    return OperationResult(True, 0, f"Added service {svc.name} to {server_ip}.", {"service": svc})


def setup_service(project: str, password: str, *, name: str) -> OperationResult:
    result = _load_session(project, password)
    if not result.success:
        return result
    session = result.data
    assert isinstance(session, MloxSession)

    svc = session.infra.get_service(name)
    if not svc:
        return OperationResult(False, 8, "Service not found in infrastructure.")

    session.infra.setup_service(svc)
    session.save_infrastructure()
    return OperationResult(True, 0, f"Service {name} set up.")


def teardown_service(project: str, password: str, *, name: str) -> OperationResult:
    result = _load_session(project, password)
    if not result.success:
        return result
    session = result.data
    assert isinstance(session, MloxSession)

    svc = session.infra.get_service(name)
    if not svc:
        return OperationResult(False, 8, "Service not found in infrastructure.")

    session.infra.teardown_service(svc)
    session.save_infrastructure()
    return OperationResult(True, 0, f"Service {name} removed.")


def service_logs(
    project: str,
    password: str,
    *,
    name: str,
    label: Optional[str] = None,
    tail: int = 200,
) -> OperationResult:
    result = _load_session(project, password)
    if not result.success:
        return result
    session = result.data
    assert isinstance(session, MloxSession)

    svc = session.infra.get_service(name)
    if not svc:
        return OperationResult(False, 8, "Service not found in infrastructure.")

    chosen_label = label
    if chosen_label is None:
        if svc.compose_service_names:
            chosen_label = next(iter(svc.compose_service_names.keys()))
        else:
            return OperationResult(
                False,
                9,
                "No compose service labels configured for this service.",
            )

    bundle = session.infra.get_bundle_by_service(svc)
    if not bundle:
        return OperationResult(False, 10, "Could not find server bundle for service.")

    with bundle.server.get_server_connection() as conn:
        logs = svc.compose_service_log_tail(conn, label=chosen_label, tail=tail)

    return OperationResult(True, 0, "Fetched service logs.", {"logs": logs})


# ---------------------------------------------------------------------------
# Config operations
# ---------------------------------------------------------------------------


def list_server_configs() -> OperationResult:
    configs = load_all_server_configs()
    payload = [
        {
            "id": cfg.id,
            "path": cfg.path,
        }
        for cfg in configs
    ]
    message = "No server configs found." if not payload else "Server configs retrieved."
    return OperationResult(True, 0, message, {"configs": payload})


def list_service_configs() -> OperationResult:
    configs = load_all_service_configs()
    payload = [
        {
            "id": cfg.id,
            "path": cfg.path,
        }
        for cfg in configs
    ]
    message = "No service configs found." if not payload else "Service configs retrieved."
    return OperationResult(True, 0, message, {"configs": payload})


# ---------------------------------------------------------------------------
# Cache control
# ---------------------------------------------------------------------------


def invalidate_session_cache(project: Optional[str] = None) -> None:
    """Clear cached sessions for a project or entirely."""

    _SESSION_CACHE.invalidate(project)
