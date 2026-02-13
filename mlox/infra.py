"""Infrastructure domain models for bundles, services, and registry-aware composition.

Purpose:
- Represent and mutate project infrastructure state, including server bundles and configured services.

Key public classes/functions:
- ``Infrastructure`` for top-level infrastructure orchestration and serialization
- ``Bundle`` for grouping services by server
- ``ModelRegistry`` and ``ModelServer`` interfaces for model-serving integrations
- ``Repo`` domain metadata container

Expected runtime mode:
- Remote executor + CLI/UI/TUI backend state management

Related modules (plain-text links):
- mlox.server
- mlox.service
- mlox.config
- mlox.session
- mlox.service_registry
"""

from abc import abstractmethod
from collections.abc import Generator
import logging

from datetime import datetime
from dataclasses import dataclass, field
from typing import Optional, List, Literal, Dict, Any

from mlox.config import (
    ServiceConfig,
    get_stacks_path,
    load_service_config_by_id,
    load_all_service_configs,
)
from mlox.service_registry import register_service, get_service_registry
from mlox.server import AbstractServer
from mlox.service import AbstractService
from mlox.utils import (
    dataclass_to_dict,
    dict_to_dataclass,
    auto_map_ports,
    generate_pw,
    generate_username,
)

logger = logging.getLogger(__name__)


@dataclass
class ModelRegistry:
    @abstractmethod
    def list_models(self, filter: str | None = None) -> List[Dict[str, Any]]:
        pass


@dataclass
class ModelServer:
    # kw_only avoids default-before-required ordering problems in subclasses
    registry_uuid: str | None = field(default=None, kw_only=True)

    @abstractmethod
    def is_model(self, name: str) -> bool:
        pass

    @abstractmethod
    def get_registry(self) -> ModelRegistry | None:
        pass


@dataclass
class Repo:
    repo_name: str = field(default="", init=False)
    created_timestamp: str = field(default_factory=datetime.now().isoformat, init=False)
    modified_timestamp: str = field(
        default_factory=datetime.now().isoformat, init=False
    )


@dataclass
class Bundle:
    name: str
    server: AbstractServer
    descr: str = field(default="", init=False)
    tags: List[str] = field(default_factory=list, init=False)
    services: List[AbstractService] = field(default_factory=list, init=False)


@dataclass
class Infrastructure:
    bundles: List[Bundle] = field(default_factory=list, init=False)
    configs: Dict[str, ServiceConfig] = field(default_factory=dict, init=False)

    def __post_init__(self):
        self.populate_configs()

    def clear_service_registry(self) -> None:
        """Clear the singleton service registry (useful for testing)"""
        from mlox.service_registry import get_service_registry

        get_service_registry().clear()

    def filter_by_group(
        self, group: str, bundle: Bundle | None = None
    ) -> List[AbstractService]:
        services: List[AbstractService] = list()
        if not bundle:
            for bundle in self.bundles:
                for s in bundle.services:
                    if group in list(self.configs[s.service_config_id].groups.keys()):
                        services.append(s)
        else:
            for s in bundle.services:
                if group in list(self.configs[s.service_config_id].groups.keys()):
                    services.append(s)
        return services

    def get_bundle_by_service(self, service: AbstractService) -> Optional[Bundle]:
        for bundle in self.bundles:
            for s in bundle.services:
                if s == service:
                    return bundle
        return None

    def get_bundle_by_ip(self, ip: str) -> Optional[Bundle]:
        for bundle in self.bundles:
            if bundle.server.ip == ip:
                return bundle
        return None

    def remove_bundle(self, bundle: Bundle) -> None:
        registry = get_service_registry()
        for service in bundle.services:
            registry.unregister_service(service.uuid)

        try:
            self.bundles.remove(bundle)
        except ValueError:
            logging.warning(f"Could not find bundle {bundle.server.ip}")
        return None

    def setup_service(self, service: AbstractService) -> None:
        bundle = self.get_bundle_by_service(service)
        if not bundle:
            logging.warning("Could not find bundle.")
            return
        with bundle.server.get_server_connection() as conn:
            service.setup(conn)
            service.spin_up(conn)

    def teardown_service(self, service: AbstractService) -> None:
        bundle = self.get_bundle_by_service(service)
        if not bundle:
            logging.warning("Could not find bundle.")
            return
        with bundle.server.get_server_connection() as conn:
            service.spin_down(conn)
            service.teardown(conn)
        bundle.services.remove(service)
        # UNREGISTER SERVICE FROM SINGLETON REGISTRY
        get_service_registry().unregister_service(service.uuid)

    def add_service(
        self,
        ip: str,
        config: ServiceConfig,
        params: Dict[str, Any],
        service: AbstractService | None = None,
    ) -> Bundle | None:
        bundle = next((v for v in self.bundles if v.server.ip == ip), None)
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
            # PART I: FILL PLACEHOLDERS
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

            # PART II: ASSIGN PORTS
            port_prefix = "${MLOX_AUTO_PORT_"
            port_postfix = "}"
            restricted_ports: Any = config.ports.pop("restricted", [])
            if not isinstance(restricted_ports, list):
                restricted_ports = list()
                logger.warning(
                    f"Restricted ports should be a list, got {type(restricted_ports)}"
                )
            used_ports: list = restricted_ports
            for s in bundle.services:
                used_ports.extend(list(s.service_ports.values()))
            assigned_ports = auto_map_ports(used_ports, config.ports)
            mlox_params.update(
                {
                    f"{port_prefix}{name.upper()}{port_postfix}": str(port)
                    for name, port in assigned_ports.items()
                }
            )
            params.update(mlox_params)

            # PART III: INSTANTIATE SERVICE
            _service = config.instantiate_service(params=params)
            if not _service:
                logger.warning("Could not instantiate service.")
                return None
            service = _service

        # ENSURE UNIQUE NAME AND CACHE CONFIG
        self.configs[str(type(service))] = config
        cntr = 0
        service_names = self.list_service_names()
        while service.name in service_names:
            service.name = service.name + "_" + str(cntr)
            cntr += 1

        # SET TASK EXECUTOR
        service.set_task_executor(bundle.server.create_new_task_executor())
        # REGISTER SERVICE IN SINGLETON REGISTRY FOR DEPENDENCY RESOLUTION
        register_service(service.uuid, service)
        # REGISTER SERVICE IN INFRASTRUCTURE
        bundle.services.append(service)
        return bundle

    def list_service_names(self) -> List[str]:
        return [s.name for bundle in self.bundles for s in bundle.services]

    def services(self) -> Generator[AbstractService]:
        for bundle in self.bundles:
            for s in bundle.services:
                yield s

    def get_service(self, service_name: str) -> AbstractService | None:
        for bundle in self.bundles:
            for s in bundle.services:
                if s.name == service_name:
                    return s
        return None

    def get_service_by_uuid(self, service_uuid: str) -> AbstractService | None:
        for bundle in self.bundles:
            for s in bundle.services:
                if s.uuid == service_uuid:
                    return s
        return None

    def get_server_by_uuid(self, server_uuid: str) -> AbstractServer | None:
        for bundle in self.bundles:
            if bundle.server.uuid == server_uuid:
                return bundle.server
        return None

    def get_service_config(
        self, service: AbstractService | AbstractServer
    ) -> ServiceConfig | None:
        if service.service_config_id in self.configs:
            return self.configs[service.service_config_id]
        else:
            config = load_service_config_by_id(service.service_config_id)
            if config:
                self.configs[service.service_config_id] = config
                return config
            else:
                logger.error(
                    f"Could not find service config for {service.service_config_id}"
                )
        return None

    def add_server(
        self, config: ServiceConfig, params: Dict[str, str]
    ) -> Bundle | None:
        server = config.instantiate_server(params=params)
        if not server:
            logging.warning("Could not instantiate server.")
            return None
        for bundle in self.bundles:
            if bundle.server.ip == server.ip:
                logging.warning("Server already exists.")
                return None
        if not server.test_connection():
            logging.warning("Could not connect to server.")
            return None

        self.configs[str(type(server))] = config
        bundle = Bundle(name=server.ip, server=server)
        self.bundles.append(bundle)
        bundle.server.discovered = datetime.now().isoformat()
        return bundle

    def list_kubernetes_controller(self) -> List[Bundle]:
        return [
            bundle
            for bundle in self.bundles
            if "kubernetes" in bundle.server.backend
            and bundle.server.state == "running"
        ]

    def filter_bundles_by_backend(
        self, backend: Literal["docker", "kubernetes"]
    ) -> List[Bundle]:
        return [b for b in self.bundles if backend in b.server.backend]

    def to_dict(self) -> Dict:
        infra_dict = dataclass_to_dict(self)
        _ = infra_dict.pop("configs", None)
        return infra_dict

    @classmethod
    def from_dict(cls, infra_dict: Dict) -> "Infrastructure":
        infra = dict_to_dataclass(infra_dict, hooks=[AbstractServer, AbstractService])
        infra.populate_configs()
        infra.populate_service_registry()
        return infra

    def populate_service_registry(self) -> None:
        registry = get_service_registry()
        for service in self.services():
            registry.register_service(service.uuid, service)

    def populate_configs(self) -> None:
        configs = load_all_service_configs(prefix="mlox")
        configs.extend(load_all_service_configs(prefix="mlox-server"))
        for config in configs:
            self.configs[config.id] = config
