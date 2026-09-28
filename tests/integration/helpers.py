from __future__ import annotations

import logging
import shlex
from typing import Any

from mlox.application.use_cases import servers, services
from mlox.config import ServiceConfig
from mlox.infra import Bundle, Infrastructure
from mlox.project.state import WorkspaceState
from mlox.service import AbstractService


def log_compose_diagnostics(service, bundle) -> None:
    """Capture container state and logs before a failed test's VM is removed."""

    if "docker" not in (getattr(bundle.server, "backend", ()) or ()):
        return
    if not getattr(service, "compose_service_names", None):
        return
    compose_path = f"{service.target_path}/{service.target_docker_script}"
    env_path = f"{service.target_path}/{service.target_docker_env}"
    prefix = (
        f"docker compose --env-file {shlex.quote(env_path)} "
        f"-f {shlex.quote(compose_path)}"
    )
    try:
        with bundle.server.get_server_connection() as conn:
            for args in ("ps --all", "logs --no-color --tail 80"):
                try:
                    result = conn.sudo(
                        f"{prefix} {args}", hide=True, warn=True, pty=False, timeout=30
                    )
                    logging.error(
                        "Readiness diagnostics for %s (%s, exit %s):\n%s\n%s",
                        service.name,
                        args,
                        result.exited,
                        result.stdout,
                        result.stderr,
                    )
                except Exception as exc:
                    logging.warning(
                        "Could not collect %s for %s: %s", args, service.name, exc
                    )
    except Exception as exc:
        logging.warning("Could not connect for readiness diagnostics: %s", exc)


def add_server(
    infrastructure: Infrastructure,
    config: ServiceConfig,
    params: dict[str, str],
) -> Bundle | None:
    project = WorkspaceState(name="integration-test", infrastructure=infrastructure)
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
    project = WorkspaceState(name="integration-test", infrastructure=infrastructure)
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


def remove_server(infrastructure: Infrastructure, server_ip: str):
    project = WorkspaceState(name="integration-test", infrastructure=infrastructure)
    return servers.teardown_server(project, ip=server_ip)


def remove_service(infrastructure: Infrastructure, service_name: str):
    project = WorkspaceState(name="integration-test", infrastructure=infrastructure)
    return services.teardown_service(project, name=service_name)
