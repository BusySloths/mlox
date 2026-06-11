from __future__ import annotations

from typing import Any

from mlox.application.use_cases import servers, services
from mlox.config import ServiceConfig
from mlox.infra import Bundle, Infrastructure
from mlox.project.aggregate import ProjectAggregate
from mlox.service import AbstractService


def add_server(
    infrastructure: Infrastructure,
    config: ServiceConfig,
    params: dict[str, str],
) -> Bundle | None:
    project = ProjectAggregate(name="integration-test", infrastructure=infrastructure)
    result = servers.add_server(
        project,
        lambda _: config,
        template_path=config.path,
        ip=params.get("${MLOX_IP}", ""),
        port=int(params.get("${MLOX_PORT}", 0)),
        root_user=params.get("${MLOX_ROOT}", ""),
        root_password=params.get("${MLOX_ROOT_PW}", ""),
        extra_params=params,
    )
    return result.data.get("bundle") if result.success else None


def add_service(
    infrastructure: Infrastructure,
    server_ip: str,
    config: ServiceConfig,
    params: dict[str, Any],
    service: AbstractService | None = None,
) -> Bundle | None:
    project = ProjectAggregate(name="integration-test", infrastructure=infrastructure)
    result = services.add_service(
        project,
        lambda _: config,
        server_ip=server_ip,
        template_id=config.id,
        params=params,
        service=service,
    )
    if not result.success:
        return None
    return infrastructure.get_bundle_by_ip(server_ip)
