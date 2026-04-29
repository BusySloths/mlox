from __future__ import annotations

from typing import Any, Dict, List, Optional

from mlox.application import infrastructure_ops as infra_use_cases
from mlox.application.result import OperationResult


def list_services(session) -> OperationResult:
    services: List[Dict[str, Any]] = []
    for bundle in session.infra.bundles:
        for svc in bundle.services:
            labels = list(getattr(svc, "compose_service_names", {}).keys())
            ports_dict = getattr(svc, "service_ports", {}) or {}
            ports = [f"{name}:{port}" for name, port in ports_dict.items()]
            urls_dict = getattr(svc, "service_urls", {}) or {}
            urls = [f"{name}: {url}" for name, url in urls_dict.items()]
            services.append(
                {
                    "name": svc.name,
                    "service_config_id": getattr(svc, "service_config_id", "unknown"),
                    "server_ip": bundle.server.ip,
                    "state": getattr(svc, "state", "unknown"),
                    "labels": labels,
                    "ports": ports,
                    "urls": urls,
                }
            )

    message = "No services found." if not services else "Services retrieved successfully."
    return OperationResult(True, 0, message, {"services": services})


def add_service(
    session,
    load_service_config,
    *,
    server_ip: str,
    template_id: str,
    params: Optional[Dict[str, str]] = None,
) -> OperationResult:
    config = load_service_config(template_id)
    if not config:
        return OperationResult(False, 6, "Service template not found.")

    bundle = infra_use_cases.add_service(
        session.infra,
        server_ip,
        config,
        params or {},
    )
    if not bundle:
        return OperationResult(False, 7, "Failed to add service to server.")

    session.save_infrastructure()
    service = bundle.services[-1]
    return OperationResult(
        True,
        0,
        f"Added service {service.name} to {server_ip}.",
        {"service": service},
    )


def setup_service(
    session,
    *,
    name: str,
) -> OperationResult:
    service = session.infra.get_service(name)
    if not service:
        return OperationResult(False, 8, "Service not found in infrastructure.")

    infra_use_cases.setup_service(session.infra, service)
    session.save_infrastructure()
    return OperationResult(True, 0, f"Service {name} set up.", {"service": service})


def teardown_service(
    session,
    *,
    name: str,
) -> OperationResult:
    service = session.infra.get_service(name)
    if not service:
        return OperationResult(False, 8, "Service not found in infrastructure.")

    infra_use_cases.teardown_service(session.infra, service)
    session.save_infrastructure()
    return OperationResult(True, 0, f"Service {name} removed.", {"service": service})


def service_logs(
    session,
    *,
    name: str,
    label: Optional[str] = None,
    tail: int = 200,
) -> OperationResult:
    service = session.infra.get_service(name)
    if not service:
        return OperationResult(False, 8, "Service not found in infrastructure.")

    chosen_label = label
    if chosen_label is None:
        compose_names = getattr(service, "compose_service_names", {})
        if compose_names:
            chosen_label = next(iter(compose_names.keys()))
        else:
            return OperationResult(
                False,
                9,
                "No compose service labels configured for this service.",
            )

    bundle = session.infra.get_bundle_by_service(service)
    if not bundle:
        return OperationResult(False, 10, "Could not find server bundle for service.")

    with bundle.server.get_server_connection() as conn:
        logs = service.compose_service_log_tail(conn, label=chosen_label, tail=tail)

    return OperationResult(True, 0, "Fetched service logs.", {"logs": logs})


def list_service_configs(list_configs) -> OperationResult:
    configs = list_configs()
    payload = [{"id": cfg.id, "path": cfg.path} for cfg in configs]
    message = "No service configs found." if not payload else "Service configs retrieved."
    return OperationResult(True, 0, message, {"configs": payload})
