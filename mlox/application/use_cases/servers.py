from __future__ import annotations

import logging
from datetime import datetime
from typing import Dict, Optional

from mlox.application.result import OperationResult
from mlox.infra import Bundle
from mlox.project.aggregate import ProjectAggregate
from mlox.utils import dataclass_to_dict

logger = logging.getLogger(__name__)


def list_servers(project: ProjectAggregate) -> OperationResult:
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
    project: ProjectAggregate,
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


def setup_server(project: ProjectAggregate, *, ip: str) -> OperationResult:
    bundle = project.infrastructure.get_bundle_by_ip(ip)
    if not bundle:
        return OperationResult(False, 5, "Server not found in infrastructure.")
    bundle.server.setup()
    return OperationResult(True, 0, f"Server {ip} set up.")


def teardown_server(project: ProjectAggregate, *, ip: str) -> OperationResult:
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
    project: ProjectAggregate,
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
