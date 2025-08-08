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
from mlox.server import AbstractServer
from mlox.service import AbstractService
from mlox.utils import (
    dataclass_to_dict,
    dict_to_dataclass,
    auto_map_ports,
    generate_pw,
    generate_username,
)

# Configure logging (optional, but recommended)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(module)s.%(funcName)s:%(lineno)d | %(message)s",
)
logger = logging.getLogger(__name__)


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
    focus: List[str] = field(default_factory=list, init=False)

    def __post_init__(self):
        self.populate_configs()

    def focus_service(self, service: AbstractService) -> None:
        if service.uuid not in self.focus:
            self.focus.append(service.uuid)

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
        try:
            self.bundles.remove(bundle)
            for s in bundle.services:
                if s.uuid in self.focus:
                    self.focus.remove(s.uuid)
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
        if service.uuid in self.focus:
            self.focus.remove(service.uuid)

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
        bundle.services.append(service)
        return bundle

    def list_service_names(self) -> List[str]:
        return [s.name for bundle in self.bundles for s in bundle.services]

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

    def list_bundles_with_backend(
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
        return infra

    def populate_configs(self) -> None:
        configs = load_all_service_configs(prefix="mlox")
        configs.extend(load_all_service_configs(prefix="mlox-server"))
        for config in configs:
            self.configs[config.id] = config
