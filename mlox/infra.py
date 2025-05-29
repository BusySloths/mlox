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
class StatefulService:
    service: AbstractService
    config: ServiceConfig
    state: Literal[
        "un-initialized",
        "setup-complete",
        "setup-failed",
        "removed",
        "running",
        "stopped",
        "unknown",
    ]


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
    services: List[StatefulService] = field(default_factory=list, init=False)
    repos: List[Repo] = field(default_factory=list, init=False)

    def initialize(self) -> None:
        if self.status != "un-initialized":
            logging.error("Can not initialize an already initialized server.")
            return
        self.server.update()
        self.server.install_packages()
        self.server.update()
        self.server.add_mlox_user()
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
            cluster_name = f"k8s-{controller.name}"
            self.tags.append(cluster_name)
            if cluster_name not in controller.tags:
                controller.tags.append(cluster_name)
        self.status = backend


@dataclass
class Infrastructure:
    bundles: List[Bundle] = field(default_factory=list, init=False)

    def get_bundle_by_ip(self, ip: str) -> Optional[Bundle]:
        for bundle in self.bundles:
            if bundle.server.ip == ip:
                return bundle
        return None

    def setup_service(
        self,
        ip: str,
        service_name: str,
        state: Literal["setup", "teardown", "spin_up", "spin_down"],
    ) -> None:
        bundle = self.get_bundle_by_ip(ip)
        if not bundle:
            logging.warning("Could not find bundle.")
            return

        stateful_service = None
        for ss in bundle.services:
            if ss.service.name == service_name:
                stateful_service = ss
                break
        if not stateful_service:
            logging.warning("Could not find service.")
            return
        with bundle.server.get_server_connection() as conn:
            if state == "setup":
                stateful_service.service.setup(conn)
                stateful_service.service.spin_up(conn)
                stateful_service.state = "running"
            elif state == "spin_up":
                stateful_service.service.spin_up(conn)
                stateful_service.state = "running"
            elif state == "spin_down":
                stateful_service.service.spin_down(conn)
                stateful_service.state = "stopped"
            elif state == "teardown":
                stateful_service.service.spin_down(conn)
                stateful_service.service.teardown(conn)
                bundle.services.remove(stateful_service)
            else:
                logging.warning("Unknown state.")

    def add_service(
        self, ip: str, config: ServiceConfig, params: Dict[str, Any]
    ) -> Bundle | None:
        bundle = next((b for b in self.bundles if b.server.ip == ip), None)
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
            "${MLOX_AUTO_USER}": "service-user",
            "${MLOX_AUTO_PW}": "service-pw",
            "${MLOX_AUTO_PORT}": "7654",
        }
        params.update(mlox_params)
        service = config.instantiate(bundle.status, params=params)
        if not service:
            logger.warning("Could not instantiate service.")
            return None

        bundle.services.append(StatefulService(service, config, state="un-initialized"))
        return bundle

    def get_stateful_service(
        self, ip: str, service_name: str
    ) -> Tuple[Bundle, StatefulService] | None:
        bundle = self.get_bundle_by_ip(ip)
        if not bundle:
            return None
        for stateful_service in bundle.services:
            if stateful_service.service.name == service_name:
                return bundle, stateful_service
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

    def create_and_add_repo(
        self, ip: str, link: str, repo_abs_root: str | None = None
    ) -> None:
        REPOS: str = "repos" if not repo_abs_root else repo_abs_root
        bundle = next(
            (bundle for bundle in self.bundles if bundle.server.ip == ip), None
        )
        if not bundle:
            return
        if not bundle.server.mlox_user:
            return

        name = link.split("/")[-1][:-4]
        if repo_abs_root:
            path = f"{repo_abs_root}/{name}"
        else:
            path = f"{bundle.server.mlox_user.home}/{REPOS}/{name}"
        repo = Repo(link=link, name=name, path=path)
        bundle.server.git_clone(repo.link, REPOS)
        bundle.repos.append(repo)

    def remove_repo(self, ip: str, repo: Repo) -> None:
        bundle = next(
            (bundle for bundle in self.bundles if bundle.server.ip == ip), None
        )
        if not bundle:
            return
        if not bundle.server.mlox_user:
            return
        bundle.server.git_remove(repo.path)
        bundle.repos.remove(repo)

    def add_server(self, config: ServerConfig, params: Dict[str, str]) -> Bundle | None:
        server = config.instantiate(params=params)
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

        bundle = Bundle(name=server.ip, config=config, server=server)
        self.bundles.append(bundle)
        return bundle

    # def delete_bundle(self, bundle: Bundle) -> None:
    #     self.bundles.remove(bundle)

    def list_kubernetes_controller(self) -> List[Bundle]:
        return [bundle for bundle in self.bundles if bundle.status == "kubernetes"]

    def list_bundles_with_backend(
        self, backend: Literal["docker", "kubernetes"]
    ) -> List[Bundle]:
        return [b for b in self.bundles if b.status == backend]

    def save(self, filepath: str, password: str) -> None:
        infra_dict = dataclass_to_dict(self)
        save_to_json(infra_dict, filepath, password, encrypt=True)

    @classmethod
    def load(cls, filepath: str, password: str) -> "Infrastructure":
        infra_dict = load_from_json(filepath, password, encrypted=True)
        return dict_to_dataclass(infra_dict, hooks=[AbstractServer, AbstractService])
