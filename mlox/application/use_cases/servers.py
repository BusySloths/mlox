from __future__ import annotations

from typing import Dict, Optional

from mlox.application.use_cases import infrastructure as infra_use_cases
from mlox.application.result import OperationResult
from mlox.utils import dataclass_to_dict


def list_servers(load_session, project: str, password: str) -> OperationResult:
    result = load_session(project, password)
    if not result.success:
        return result

    session = result.data
    servers = []
    for bundle in session.infra.bundles:
        servers.append(
            {
                "ip": bundle.server.ip,
                "state": getattr(bundle.server, "state", "unknown"),
                "service_count": len(bundle.services),
                "service_config_id": getattr(bundle.server, "service_config_id", None),
                "port": getattr(bundle.server, "port", None),
                "discovered": getattr(bundle.server, "discovered", None),
                "backend": getattr(bundle.server, "backend", None) or [],
            }
        )

    message = "No servers found." if not servers else "Servers retrieved successfully."
    return OperationResult(True, 0, message, {"servers": servers})


def add_server(
    load_session,
    load_server_config,
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
    result = load_session(project, password)
    if not result.success:
        return result

    config = load_server_config(template_path)
    if config is None:
        return OperationResult(False, 3, "Server template not found.")

    session = result.data
    params = {
        "${MLOX_IP}": ip,
        "${MLOX_PORT}": str(port),
        "${MLOX_ROOT}": root_user,
        "${MLOX_ROOT_PW}": root_password,
    }
    if extra_params:
        params.update(extra_params)

    bundle = infra_use_cases.add_server(session.infra, config, params)
    if not bundle:
        return OperationResult(
            False,
            4,
            "Failed to add server to the project infrastructure.",
        )

    session.save_infrastructure()
    return OperationResult(True, 0, f"Added server {ip}.", {"bundle": bundle})


def setup_server(load_session, project: str, password: str, *, ip: str) -> OperationResult:
    result = load_session(project, password)
    if not result.success:
        return result

    session = result.data
    bundle = session.infra.get_bundle_by_ip(ip)
    if not bundle:
        return OperationResult(False, 5, "Server not found in infrastructure.")

    infra_use_cases.setup_server(bundle.server)
    session.save_infrastructure()
    return OperationResult(True, 0, f"Server {ip} set up.")


def teardown_server(
    load_session,
    project: str,
    password: str,
    *,
    ip: str,
) -> OperationResult:
    result = load_session(project, password)
    if not result.success:
        return result

    session = result.data
    bundle = session.infra.get_bundle_by_ip(ip)
    if not bundle:
        return OperationResult(False, 5, "Server not found in infrastructure.")

    infra_use_cases.teardown_server(bundle.server)
    infra_use_cases.remove_bundle(session.infra, bundle)
    session.save_infrastructure()
    return OperationResult(True, 0, f"Server {ip} removed from infrastructure.")


def save_server_key(
    load_session,
    save_json,
    project: str,
    password: str,
    *,
    ip: str,
    output_path: str,
) -> OperationResult:
    result = load_session(project, password)
    if not result.success:
        return result

    session = result.data
    bundle = session.infra.get_bundle_by_ip(ip)
    if not bundle:
        return OperationResult(False, 5, "Server not found in infrastructure.")

    server_dict = dataclass_to_dict(bundle.server)
    save_json(server_dict, output_path, password, True)
    return OperationResult(True, 0, f"Saved key for {ip} to {output_path}.")


def list_server_configs(list_configs) -> OperationResult:
    configs = list_configs()
    payload = [{"id": cfg.id, "path": cfg.path} for cfg in configs]
    message = "No server configs found." if not payload else "Server configs retrieved."
    return OperationResult(True, 0, message, {"configs": payload})
