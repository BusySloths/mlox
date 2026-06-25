from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, Optional

from mlox.application.result import OperationResult
from mlox.config import load_all_server_configs
from mlox.infra import Bundle
from mlox.project.state import WorkspaceState
from mlox.server import ServerCapability
from mlox.terminal import (
    TerminalLaunchError,
    launch_external_ssh_terminal,
    resolve_ssh_launch_spec,
)
from mlox.utils import dataclass_to_dict

logger = logging.getLogger(__name__)


def list_servers(project: WorkspaceState) -> OperationResult:
    payload = [
        {
            "ip": bundle.server.ip,
            "state": getattr(bundle.server, "state", "unknown"),
            "service_count": len(bundle.services),
            "service_config_id": getattr(bundle.server, "service_config_id", None),
            "port": getattr(bundle.server, "port", None),
            "discovered": getattr(bundle.server, "discovered", None),
            "backend": getattr(bundle.server, "backend", None) or [],
        }
        for bundle in project.infrastructure.bundles
    ]
    message = "No servers found." if not payload else "Servers retrieved successfully."
    return OperationResult(True, 0, message, {"servers": payload})


def add_server(
    project: WorkspaceState,
    load_server_config,
    *,
    template_path: str,
    ip: str,
    port: int,
    root_user: str,
    root_password: str,
    extra_params: Optional[Dict[str, str]] = None,
) -> OperationResult:
    config = load_server_config(template_path)
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

    server = config.instantiate_server(params=params)
    if not server:
        return OperationResult(False, 4, "Failed to instantiate server.")
    infra = project.infrastructure
    if infra.get_bundle_by_ip(server.ip):
        return OperationResult(False, 4, "Server already exists.")
    if not server.test_connection():
        return OperationResult(False, 4, "Could not connect to server.")

    infra.configs[config.id] = config
    bundle = Bundle(name=server.ip, server=server)
    infra.bundles.append(bundle)
    server.discovered = datetime.now().isoformat()
    return OperationResult(True, 0, f"Added server {ip}.", {"bundle": bundle})


def setup_server(project: WorkspaceState, *, ip: str) -> OperationResult:
    bundle = project.infrastructure.get_bundle_by_ip(ip)
    if not bundle:
        return OperationResult(False, 5, "Server not found in infrastructure.")
    bundle.server.setup()
    return OperationResult(True, 0, f"Server {ip} set up.")


def teardown_server(project: WorkspaceState, *, ip: str) -> OperationResult:
    infra = project.infrastructure
    bundle = infra.get_bundle_by_ip(ip)
    if not bundle:
        return OperationResult(False, 5, "Server not found in infrastructure.")
    bundle.server.teardown()
    for service in bundle.services:
        service.clear_service_lookup()
    infra.bundles.remove(bundle)
    return OperationResult(True, 0, f"Server {ip} removed from infrastructure.")


def save_server_key(
    project: WorkspaceState,
    save_json,
    password: str,
    *,
    ip: str,
    output_path: str,
) -> OperationResult:
    bundle = project.infrastructure.get_bundle_by_ip(ip)
    if not bundle:
        return OperationResult(False, 5, "Server not found in infrastructure.")
    save_json(dataclass_to_dict(bundle.server), output_path, password, True)
    return OperationResult(True, 0, f"Saved key for {ip} to {output_path}.")


def list_server_configs(list_configs) -> OperationResult:
    payload = [{"id": cfg.id, "path": cfg.path} for cfg in list_configs()]
    message = "No server configs found." if not payload else "Server configs retrieved."
    return OperationResult(True, 0, message, {"configs": payload})


def browse_server_templates(
    list_configs=None,
) -> OperationResult:
    """Return server template config objects for UI browsing."""

    list_configs = list_configs or load_all_server_configs
    configs = list(list_configs())
    message = "No server templates found." if not configs else "Server templates loaded."
    return OperationResult(True, 0, message, {"configs": configs})


def open_server_terminal(
    server,
    launcher=None,
) -> OperationResult:
    """Open an external terminal for a server selection."""

    if not server:
        return OperationResult(False, 12, "No server selected.")
    terminal_capability = can_open_server_terminal(server)
    if not terminal_capability.success:
        return terminal_capability
    launcher = launcher or launch_external_ssh_terminal
    try:
        launched = launcher(server)
    except TerminalLaunchError as exc:
        return OperationResult(False, 13, str(exc))

    return OperationResult(
        True,
        0,
        f"Opened SSH terminal for {getattr(server, 'ip', 'server')}.",
        {"launch": launched},
    )


def can_open_server_terminal(server) -> OperationResult:
    """Return whether the selected server can open an interactive SSH terminal."""

    if not server:
        return OperationResult(False, 12, "No server selected.")
    if ServerCapability.TERMINAL.value not in _server_capability_names(server):
        return OperationResult(
            False,
            13,
            "The selected server does not support terminal login.",
        )
    try:
        resolve_ssh_launch_spec(server)
    except TerminalLaunchError as exc:
        return OperationResult(False, 13, str(exc))

    return OperationResult(
        True,
        0,
        f"SSH terminal is available for {getattr(server, 'ip', 'server')}.",
        {"server": server},
    )


def _server_capability_names(server) -> set[str]:
    return {
        capability.value if hasattr(capability, "value") else str(capability)
        for capability in getattr(server, "capabilities", set())
    }


def get_server_runtime_info(server, *, no_cache: bool = True) -> OperationResult:
    """Collect server and backend information for UI adapters."""

    if not server:
        return OperationResult(False, 14, "No server selected.")

    data: Dict[str, Any] = {}
    errors: list[str] = []

    server_info = get_server_info(server, no_cache=no_cache)
    if server_info.success:
        data.update(server_info.data or {})
    else:
        errors.append(server_info.message)

    backend_info = get_backend_info(server)
    if backend_info.success:
        data.update(backend_info.data or {})
    else:
        errors.append(backend_info.message)

    if errors and "server_info" not in data and "backend_info" not in data:
        return OperationResult(
            False,
            15,
            "Failed to load server information: " + "; ".join(errors),
            {"errors": errors},
        )

    if errors:
        data["errors"] = errors
    return OperationResult(True, 0, "Loaded server information.", data)


def get_server_info(server, *, no_cache: bool = True) -> OperationResult:
    """Collect host/server information for UI adapters."""

    if not server:
        return OperationResult(False, 14, "No server selected.")

    try:
        return OperationResult(
            True,
            0,
            "Loaded server information.",
            {"server_info": server.get_server_info(no_cache=no_cache)},
        )
    except Exception as exc:
        return OperationResult(False, 15, f"Failed to load server info: {exc}")


def get_backend_info(server) -> OperationResult:
    """Collect backend status information for UI adapters."""

    if not server:
        return OperationResult(False, 14, "No server selected.")

    backend_info = getattr(server, "get_backend_info", None)
    if not callable(backend_info):
        backend_info = getattr(server, "get_backend_status", None)

    if callable(backend_info):
        try:
            return OperationResult(
                True,
                0,
                "Loaded backend information.",
                {"backend_info": backend_info()},
            )
        except Exception as exc:
            return OperationResult(False, 15, f"Failed to load backend info: {exc}")

    return OperationResult(True, 0, "No backend information available.", {"backend_info": {}})
