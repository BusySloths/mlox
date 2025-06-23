import logging

from datetime import datetime
from dataclasses import dataclass, field
from typing import Optional, List, Literal, Tuple, Dict, Any

from mlox.config import ServiceConfig
from mlox.server import AbstractServer
from mlox.service import AbstractService
from mlox.utils import (
    dataclass_to_dict,
    dict_to_dataclass,
    save_to_json,
    load_from_json,
    auto_map_ports,
    generate_pw,
    generate_username,
)

# Configure logging (optional, but recommended)
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


@dataclass
class Repo:
    link: str
    name: str
    path: str
    added_timestamp: str = field(default_factory=datetime.now().isoformat, init=False)
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

    def filter_by_group(
        self, group: str, bundle: Bundle | None = None
    ) -> List[AbstractService]:
        services: List[AbstractService] = list()
        if not bundle:
            for bundle in self.bundles:
                for s in bundle.services:
                    if group in list(self.configs[str(type(s))].groups.keys()):
                        services.append(s)
        else:
            for s in bundle.services:
                if group in list(self.configs[str(type(s))].groups.keys()):
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

    def setup_service(
        self,
        ip: str,
        service_name: str,
        state: Literal["setup", "teardown"],
    ) -> None:
        bundle = self.get_bundle_by_ip(ip)
        if not bundle:
            logging.warning("Could not find bundle.")
            return

        service = None
        for s in bundle.services:
            if s.name == service_name:
                service = s
                break
        if not service:
            logging.warning("Could not find service.")
            return
        with bundle.server.get_server_connection() as conn:
            if state == "setup":
                service.setup(conn)
                service.spin_up(conn)
            elif state == "teardown":
                service.spin_down(conn)
                service.teardown(conn)
            else:
                logging.warning("Unknown state.")

    def add_service(
        self, ip: str, config: ServiceConfig, params: Dict[str, Any]
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

        mlox_params = {
            "${MLOX_STACKS_PATH}": "./stacks/",
            "${MLOX_USER}": bundle.server.mlox_user.name,
            "${MLOX_AUTO_USER}": generate_username(),
            "${MLOX_AUTO_PW}": generate_pw(),
        }

        port_prefix = "${MLOX_AUTO_PORT_"
        port_postfix = "}"
        used_ports = list()
        for s in bundle.services:
            used_ports.extend(list(s.service_ports.values()))
        assigned_ports = auto_map_ports(used_ports, config.ports)
        mlox_params.update(
            {
                f"{port_prefix}{name.upper()}{port_postfix}": str(port)
                for name, port in assigned_ports.items()
            }
        )
        print(f"MLOX PARAMS: {mlox_params}")
        params.update(mlox_params)
        service = config.instantiate_service(params=params)
        if not service:
            logger.warning("Could not instantiate service.")
            return None
        if service.name in [s.name for s in bundle.services]:
            logger.warning(f"Service {service.name} already exists in bundle {bundle}.")
            return None

        self.configs[str(type(service))] = config
        # choose unique name
        service.name = service.__class__.__name__
        service_names = self.list_service_names()
        cntr = 0
        while service in service_names:
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

    # def pull_repo(self, ip: str, name: str) -> None:
    #     bundle = next((b for b in self.bundles if b.server.ip == ip), None)
    #     if not bundle:
    #         return
    #     repo = next((r for r in bundle.repos if r.name == name), None)
    #     if not repo:
    #         return
    #     repo.modified_timestamp = datetime.now().isoformat()
    #     bundle.server.git_pull(repo.path)

    # def create_and_add_repo(
    #     self, ip: str, link: str, repo_abs_root: str | None = None
    # ) -> None:
    #     REPOS: str = "repos" if not repo_abs_root else repo_abs_root
    #     bundle = next(
    #         (bundle for bundle in self.bundles if bundle.server.ip == ip), None
    #     )
    #     if not bundle:
    #         return
    #     if not bundle.server.mlox_user:
    #         return

    #     name = link.split("/")[-1][:-4]
    #     if repo_abs_root:
    #         path = f"{repo_abs_root}/{name}"
    #     else:
    #         path = f"{bundle.server.mlox_user.home}/{REPOS}/{name}"
    #     repo = Repo(link=link, name=name, path=path)
    #     bundle.server.git_clone(repo.link, REPOS)
    #     bundle.repos.append(repo)

    # def remove_repo(self, ip: str, repo: Repo) -> None:
    #     bundle = next(
    #         (bundle for bundle in self.bundles if bundle.server.ip == ip), None
    #     )
    #     if not bundle:
    #         return
    #     if not bundle.server.mlox_user:
    #         return
    #     bundle.server.git_remove(repo.path)
    #     bundle.repos.remove(repo)

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
        return bundle

    def clear_backend(self, ip: str) -> None:
        bundle = self.get_bundle_by_ip(ip)
        if not bundle:
            logging.warning("Could not find bundle with IP %s", ip)
            return
        bundle.server.stop_backend_runtime()
        bundle.server.teardown_backend()

    def list_kubernetes_controller(self) -> List[Bundle]:
        return [
            bundle for bundle in self.bundles if "kubernetes" in bundle.server.backend
        ]

    def list_bundles_with_backend(
        self, backend: Literal["docker", "kubernetes"]
    ) -> List[Bundle]:
        return [b for b in self.bundles if backend in b.server.backend]

    # def save(self, filepath: str, password: str) -> None:
    #     infra_dict = dataclass_to_dict(self)
    #     save_to_json(infra_dict, filepath, password, encrypt=True)

    def to_dict(self) -> Dict:
        infra_dict = dataclass_to_dict(self)
        # _ = infra_dict.pop("configs", None)
        return infra_dict

    @classmethod
    def from_dict(cls, infra_dict: Dict) -> "Infrastructure":
        infra = dict_to_dataclass(infra_dict, hooks=[AbstractServer, AbstractService])
        return infra

    @classmethod
    def load(cls, filepath: str, password: str) -> "Infrastructure":
        infra_dict = load_from_json(filepath, password, encrypted=True)
        return dict_to_dataclass(infra_dict, hooks=[AbstractServer, AbstractService])
