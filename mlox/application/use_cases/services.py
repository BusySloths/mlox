from __future__ import annotations

from typing import Any, Dict, List, Optional

from mlox.application.result import OperationResult
from mlox.config import get_stacks_path
from mlox.project.state import WorkspaceState
from mlox.service import AbstractService
from mlox.utils import auto_map_ports, generate_pw, generate_username


def list_services(project: WorkspaceState) -> OperationResult:
    payload: List[Dict[str, Any]] = []
    for bundle in project.infrastructure.bundles:
        for service in bundle.services:
            payload.append(
                {
                    "name": service.name,
                    "service_config_id": getattr(
                        service, "service_config_id", "unknown"
                    ),
                    "server_ip": bundle.server.ip,
                    "state": getattr(service, "state", "unknown"),
                    "labels": list(
                        getattr(service, "compose_service_names", {}).keys()
                    ),
                    "ports": [
                        f"{name}:{port}"
                        for name, port in (
                            getattr(service, "service_ports", {}) or {}
                        ).items()
                    ],
                    "urls": [
                        f"{name}: {url}"
                        for name, url in (
                            getattr(service, "service_urls", {}) or {}
                        ).items()
                    ],
                }
            )
    message = "No services found." if not payload else "Services retrieved successfully."
    return OperationResult(True, 0, message, {"services": payload})


def add_service(
    project: WorkspaceState,
    load_service_config,
    *,
    server_ip: str,
    template_id: str,
    params: Optional[Dict[str, str]] = None,
    service: AbstractService | None = None,
) -> OperationResult:
    config = load_service_config(template_id)
    if not config:
        return OperationResult(False, 6, "Service template not found.")
    infra = project.infrastructure
    bundle = infra.get_bundle_by_ip(server_ip)
    if not bundle or not bundle.server or not bundle.server.mlox_user:
        return OperationResult(False, 7, "Failed to add service to server.")

    values: Dict[str, Any] = dict(params or {})
    if service is None:
        values.update(
            {
                "${MLOX_STACKS_PATH}": get_stacks_path(),
                "${MLOX_USER}": bundle.server.mlox_user.name,
                "${MLOX_USER_HOME}": bundle.server.mlox_user.home,
                "${MLOX_AUTO_USER}": generate_username(),
                "${MLOX_AUTO_PW}": generate_pw(),
                "${MLOX_AUTO_API_KEY}": generate_pw(),
                "${MLOX_SERVER_IP}": bundle.server.ip,
                "${MLOX_SERVER_UUID}": bundle.server.uuid,
            }
        )
        ports = dict(config.ports)
        restricted = ports.pop("restricted", [])
        used_ports = list(restricted) if isinstance(restricted, list) else []
        for existing in bundle.services:
            used_ports.extend(existing.service_ports.values())
        values.update(
            {
                f"${{MLOX_AUTO_PORT_{name.upper()}}}": str(port)
                for name, port in auto_map_ports(used_ports, ports).items()
            }
        )
        service = config.instantiate_service(params=values)
    if not service:
        return OperationResult(False, 7, "Failed to instantiate service.")

    existing_names = infra.list_service_names()
    base_name = service.name
    counter = 0
    while service.name in existing_names:
        service.name = f"{base_name}_{counter}"
        counter += 1
    infra.configs[config.id] = config
    service.set_task_executor(bundle.server.create_new_task_executor())
    service.bind_service_lookup(infra)
    bundle.services.append(service)
    return OperationResult(
        True,
        0,
        f"Added service {service.name} to {server_ip}.",
        {"service": service},
    )


def setup_service(project: WorkspaceState, *, name: str) -> OperationResult:
    infra = project.infrastructure
    service = infra.get_service(name)
    if not service:
        return OperationResult(False, 8, "Service not found in infrastructure.")
    bundle = infra.get_bundle_by_service(service)
    if not bundle:
        return OperationResult(False, 10, "Could not find server bundle for service.")
    with bundle.server.get_server_connection() as conn:
        service.setup(conn)
        service.spin_up(conn)
    return OperationResult(True, 0, f"Service {name} set up.", {"service": service})


def teardown_service(project: WorkspaceState, *, name: str) -> OperationResult:
    infra = project.infrastructure
    service = infra.get_service(name)
    if not service:
        return OperationResult(False, 8, "Service not found in infrastructure.")
    bundle = infra.get_bundle_by_service(service)
    if not bundle:
        return OperationResult(False, 10, "Could not find server bundle for service.")
    with bundle.server.get_server_connection() as conn:
        service.spin_down(conn)
        service.teardown(conn)
    bundle.services.remove(service)
    service.clear_service_lookup()
    return OperationResult(True, 0, f"Service {name} removed.", {"service": service})


def start_service(project: WorkspaceState, *, name: str) -> OperationResult:
    infra = project.infrastructure
    service = infra.get_service(name)
    if not service:
        return OperationResult(False, 8, "Service not found in infrastructure.")
    bundle = infra.get_bundle_by_service(service)
    if not bundle:
        return OperationResult(False, 10, "Could not find server bundle for service.")
    with bundle.server.get_server_connection() as conn:
        service.spin_up(conn)
    return OperationResult(True, 0, f"Service {name} started.", {"service": service})


def stop_service(project: WorkspaceState, *, name: str) -> OperationResult:
    infra = project.infrastructure
    service = infra.get_service(name)
    if not service:
        return OperationResult(False, 8, "Service not found in infrastructure.")
    bundle = infra.get_bundle_by_service(service)
    if not bundle:
        return OperationResult(False, 10, "Could not find server bundle for service.")
    with bundle.server.get_server_connection() as conn:
        service.spin_down(conn)
    return OperationResult(True, 0, f"Service {name} stopped.", {"service": service})


def rename_service(project: WorkspaceState, *, name: str, new_name: str) -> OperationResult:
    infra = project.infrastructure
    service = infra.get_service(name)
    if not service:
        return OperationResult(False, 8, "Service not found in infrastructure.")
    if new_name in infra.list_service_names():
        return OperationResult(False, 11, "Service name must be unique.")
    service.name = new_name
    return OperationResult(
        True,
        0,
        f"Service {name} renamed to {new_name}.",
        {"service": service},
    )


def service_logs(
    project: WorkspaceState,
    *,
    name: str,
    label: Optional[str] = None,
    tail: int = 200,
) -> OperationResult:
    infra = project.infrastructure
    service = infra.get_service(name)
    if not service:
        return OperationResult(False, 8, "Service not found in infrastructure.")
    chosen_label = label
    if chosen_label is None:
        compose_names = getattr(service, "compose_service_names", {})
        if not compose_names:
            return OperationResult(
                False, 9, "No compose service labels configured for this service."
            )
        chosen_label = next(iter(compose_names))
    bundle = infra.get_bundle_by_service(service)
    if not bundle:
        return OperationResult(False, 10, "Could not find server bundle for service.")
    with bundle.server.get_server_connection() as conn:
        logs = service.compose_service_log_tail(conn, label=chosen_label, tail=tail)
    return OperationResult(True, 0, "Fetched service logs.", {"logs": logs})


def list_service_configs(list_configs) -> OperationResult:
    payload = [{"id": cfg.id, "path": cfg.path} for cfg in list_configs()]
    message = "No service configs found." if not payload else "Service configs retrieved."
    return OperationResult(True, 0, message, {"configs": payload})
