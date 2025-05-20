import logging


from datetime import datetime
from dataclasses import dataclass, field
from typing import Optional, List, Literal, Tuple, Dict, Any

from mlox.config import ServerConfig, ServiceConfig
from mlox.server import AbstractServer
from mlox.service import AbstractService
from mlox.utils import (
    dataclass_to_dict,
    dict_to_dataclass,
    save_to_json,
    load_from_json,
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
    config: ServerConfig
    server: AbstractServer
    descr: str = field(default="", init=False)
    tags: List[str] = field(default_factory=list, init=False)
    status: Literal[
        "un-initialized", "no-backend", "docker", "kubernetes", "kubernetes-agent"
    ] = field(default="un-initialized")
    services: List[Tuple[ServiceConfig, AbstractService]] = field(
        default_factory=list, init=False
    )
    repos: List[Repo] = field(default_factory=list, init=False)

    def initialize(self) -> None:
        if self.status != "un-initialized":
            logging.error("Can not initialize an already initialized server.")
            return
        self.server.update()
        self.server.install_packages()
        self.server.update()
        self.server.setup_users()
        self.server.disable_password_authentication()
        self.status = "no-backend"

    def set_backend(
        self,
        backend: Literal["docker", "kubernetes", "kubernetes-agent"],
        controller: Any | None = None,
    ) -> None:
        if backend == "docker":
            self.server.setup_docker()
            self.server.start_docker_runtime()
        elif backend == "kubernetes":
            self.server.setup_kubernetes()
            self.server.start_kubernetes_runtime()
        elif backend == "kubernetes-agent" and controller:
            stats = controller.server.get_kubernetes_status()
            if "k3s.token" not in stats:
                logging.error(
                    "Token is missing in controller stats ip: %s", controller.server.ip
                )
                return
            url = f"https://{controller.server.ip}:6443"
            token = stats["k3s.token"]
            self.server.setup_kubernetes(controller_url=url, controller_token=token)
            self.server.start_kubernetes_runtime()
        self.status = backend


@dataclass
class Infrastructure:
    bundles: List[Bundle] = field(default_factory=list, init=False)

    def get_bundle_by_ip(self, ip: str) -> Optional[Bundle]:
        for bundle in self.bundles:
            if bundle.server.ip == ip:
                return bundle
        return None

    def pull_repo(self, ip: str, name: str) -> None:
        bundle = next((b for b in self.bundles if b.server.ip == ip), None)
        if not bundle:
            return
        repo = next((r for r in bundle.repos if r.name == name), None)
        if not repo:
            return
        repo.modified_timestamp = datetime.now().isoformat()
        bundle.server.git_pull(repo.path)

    def add_repo(self, ip: str, link: str) -> None:
        bundle = next(
            (bundle for bundle in self.bundles if bundle.server.ip == ip), None
        )
        if not bundle:
            return

        REPOS: str = "repos3"
        name = link.split("/")[-1][:-4]
        path = f"{REPOS}/{name}"
        repo = Repo(link=link, name=name, path=path)
        bundle.server.git_clone(repo.link, REPOS)
        bundle.repos.append(repo)

    def add_server(self, config: ServerConfig, params: Dict[str, str]) -> Bundle | None:
        server = config.instantiate(params=params)
        if server:
            bundle = Bundle(name=server.ip, config=config, server=server)
            self.bundles.append(bundle)
            return bundle
        else:
            logging.warning("Could not add server.")
        return None

    # def delete_bundle(self, bundle: Bundle) -> None:
    #     self.bundles.remove(bundle)

    def list_kubernetes_controller(self) -> List[Bundle]:
        return [bundle for bundle in self.bundles if bundle.status == "kubernetes"]

    def list_bundles_with_backend(
        self, backend: Literal["docker", "kubernetes"]
    ) -> List[Bundle]:
        return [b for b in self.bundles if b.status == backend]

    # def add_k8s_client(self, controller: Bundle, agent: Bundle) -> None:
    #     # TODO first check/validate if possible to combine target and client (ie. check if both are k8s backends, no services, etc)
    #     token = controller.server.get_kubernetes_token()
    #     url = f"https://{controller.server.ip}:6443"
    #     agent.server.install_kubernetes(controller_url=url, controller_token=token)
    #     controller.cluster.append(agent.server)
    #     self.delete_bundle(agent)

    # def remove_k8s_client(self, controller: Bundle, agent: AbstractServer) -> Bundle:
    #     # TODO first check/validate if possible to combine target and client (ie. check if both are k8s backends, no services, etc)
    #     bundle = Bundle(name=agent.ip, server=agent)
    #     self.bundles.append(bundle)
    #     controller.cluster.remove(agent)
    #     return bundle

    def save(self, filepath: str, password: str) -> None:
        infra_dict = dataclass_to_dict(self)
        save_to_json(infra_dict, filepath, password, encrypt=True)

    @classmethod
    def load(cls, filepath: str, password: str) -> "Infrastructure":
        infra_dict = load_from_json(filepath, password, encrypted=True)
        return dict_to_dataclass(infra_dict, hooks=[AbstractServer, AbstractService])
