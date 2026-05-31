from __future__ import annotations

import logging

from datetime import datetime
from typing import TYPE_CHECKING, Any, Dict

from mlox.config import (
    get_stacks_path,
    load_all_service_configs,
    load_service_config_by_id,
)
from mlox.utils import auto_map_ports, generate_pw, generate_username

if TYPE_CHECKING:
    from mlox.config import ServiceConfig
    from mlox.infra import Bundle, Infrastructure
    from mlox.server import AbstractServer
    from mlox.service import AbstractService


logger = logging.getLogger(__name__)


def bind_service_lookups(infra: Infrastructure) -> None:
    for service in infra.services():
        service.bind_service_lookup(infra)


def clear_service_lookups(infra: Infrastructure) -> None:
    for service in infra.services():
        service.clear_service_lookup()


def remove_bundle(infra: Infrastructure, bundle: Bundle) -> None:
    for service in bundle.services:
        service.clear_service_lookup()

    try:
        bundle.server.teardown()
    except Exception:
        logger.exception(
            "Could not teardown server %s before removal.",
            bundle.server.ip,
        )
        raise

    try:
        infra.bundles.remove(bundle)
    except ValueError:
        logger.warning("Could not find bundle %s", bundle.server.ip)


def setup_server(server: AbstractServer) -> None:
    server.setup()


def teardown_server(server: AbstractServer) -> None:
    server.teardown()


def setup_service(infra: Infrastructure, service: AbstractService) -> None:
    bundle = infra.get_bundle_by_service(service)
    if not bundle:
        logger.warning("Could not find bundle.")
        return

    with bundle.server.get_server_connection() as conn:
        service.setup(conn)
        service.spin_up(conn)


def teardown_service(infra: Infrastructure, service: AbstractService) -> None:
    bundle = infra.get_bundle_by_service(service)
    if not bundle:
        logger.warning("Could not find bundle.")
        return

    with bundle.server.get_server_connection() as conn:
        service.spin_down(conn)
        service.teardown(conn)

    bundle.services.remove(service)
    service.clear_service_lookup()


def add_service(
    infra: Infrastructure,
    ip: str,
    config: ServiceConfig,
    params: Dict[str, Any],
    service: AbstractService | None = None,
) -> Bundle | None:
    bundle = next((value for value in infra.bundles if value.server.ip == ip), None)
    if not bundle:
        logger.warning("No bundle found for server.")
        return None
    if not bundle.server:
        logger.warning("No server found for bundle.")
        return None
    if not bundle.server.mlox_user:
        logger.warning("No mlox user found for bundle.")
        return None

    if not service:
        mlox_params = {
            "${MLOX_STACKS_PATH}": get_stacks_path(),
            "${MLOX_USER}": bundle.server.mlox_user.name,
            "${MLOX_USER_HOME}": bundle.server.mlox_user.home,
            "${MLOX_AUTO_USER}": generate_username(),
            "${MLOX_AUTO_PW}": generate_pw(),
            "${MLOX_AUTO_API_KEY}": generate_pw(),
            "${MLOX_SERVER_IP}": bundle.server.ip,
            "${MLOX_SERVER_UUID}": bundle.server.uuid,
        }

        port_prefix = "${MLOX_AUTO_PORT_"
        port_postfix = "}"
        restricted_ports: Any = config.ports.pop("restricted", [])
        if not isinstance(restricted_ports, list):
            restricted_ports = []
            logger.warning(
                "Restricted ports should be a list, got %s",
                type(restricted_ports),
            )
        used_ports = restricted_ports
        for existing_service in bundle.services:
            used_ports.extend(list(existing_service.service_ports.values()))
        assigned_ports = auto_map_ports(used_ports, config.ports)
        mlox_params.update(
            {
                f"{port_prefix}{name.upper()}{port_postfix}": str(port)
                for name, port in assigned_ports.items()
            }
        )
        params.update(mlox_params)

        instantiated_service = config.instantiate_service(params=params)
        if not instantiated_service:
            logger.warning("Could not instantiate service.")
            return None
        service = instantiated_service

    infra.configs[str(type(service))] = config
    counter = 0
    service_names = infra.list_service_names()
    while service.name in service_names:
        service.name = service.name + "_" + str(counter)
        counter += 1

    service.set_task_executor(bundle.server.create_new_task_executor())
    service.bind_service_lookup(infra)
    bundle.services.append(service)
    return bundle


def get_service_config(
    infra: Infrastructure,
    service: AbstractService | AbstractServer,
) -> ServiceConfig | None:
    if service.service_config_id in infra.configs:
        return infra.configs[service.service_config_id]

    config = load_service_config_by_id(service.service_config_id)
    if config:
        infra.configs[service.service_config_id] = config
        return config

    logger.error("Could not find service config for %s", service.service_config_id)
    return None


def add_server(
    infra: Infrastructure,
    config: ServiceConfig,
    params: Dict[str, str],
) -> Bundle | None:
    from mlox.infra import Bundle

    server = config.instantiate_server(params=params)
    if not server:
        logger.warning("Could not instantiate server.")
        return None
    for bundle in infra.bundles:
        if bundle.server.ip == server.ip:
            logger.warning("Server already exists.")
            return None
    if not server.test_connection():
        logger.warning("Could not connect to server.")
        return None

    infra.configs[str(type(server))] = config
    bundle = Bundle(name=server.ip, server=server)
    infra.bundles.append(bundle)
    bundle.server.discovered = datetime.now().isoformat()
    return bundle


def populate_service_registry(infra: Infrastructure) -> None:
    bind_service_lookups(infra)


def populate_configs(infra: Infrastructure) -> None:
    configs = load_all_service_configs(prefix="mlox")
    configs.extend(load_all_service_configs(prefix="mlox-server"))
    for config in configs:
        infra.configs[config.id] = config
