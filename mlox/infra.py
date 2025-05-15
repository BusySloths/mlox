import logging

from dataclasses import dataclass, field
from typing import Optional, List, Literal

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
class Bundle:
    name: str
    server: AbstractServer
    descr: str = field(default="", init=False)
    tags: List[str] = field(default_factory=list, init=False)
    backend: Literal["un-initialized", "docker", "kubernetes"] = field(
        default="un-initialized"
    )
    cluster: List[AbstractServer] = field(default_factory=list, init=False)
    services: List[AbstractService] = field(default_factory=list, init=False)

    def __post_init__(self):
        if self.backend == "docker" and not self.server:
            raise ValueError("Docker bundles need a 'server'.")
        if self.backend == "kubernetes":
            if not self.server:
                raise ValueError("Kubernetes bundles need a control plane in 'server'.")
            if not self.cluster:
                print("⚠️ Warning: Kubernetes cluster has no worker nodes.")

    def initialize(self) -> None:
        if self.backend != "un-initialized":
            logging.error("Can not initialize an already initialized server.")
            return
        self.server.update()
        self.server.install_packages()
        self.server.update()
        self.server.setup_users()
        self.server.install_docker()
        self.server.install_kubernetes()
        self.server.update()
        self.server.disable_password_authentication()
        self.backend = "docker"
        self.server.switch_backend(from_backend="kubernetes")

    def switch_backend(self) -> None:
        if self.backend == "un-initialized":
            logging.error("Can not switch backend of an un-initialized server.")
            return
        new_backend = self.server.switch_backend(from_backend=self.backend)
        if self.backend == new_backend:
            logging.error("Could not change backend.")
        self.backend = new_backend


@dataclass
class Infrastructure:
    bundles: List[Bundle] = field(default_factory=list, init=False)

    def get_bundle_by_ip(self, ip: str) -> Optional[Bundle]:
        for bundle in self.bundles:
            if bundle.server.ip == ip:
                return bundle
        return None

    def add_server(self, server: AbstractServer) -> Bundle:
        bundle = Bundle(name=server.ip, server=server)
        self.bundles.append(bundle)
        return bundle

    def delete_bundle(self, bundle: Bundle) -> None:
        self.bundles.remove(bundle)

    def list_available_k8s_clients(self, target: Bundle) -> List[Bundle]:
        return [
            bundle
            for bundle in self.bundles
            if bundle.backend == "kubernetes" and bundle != target
        ]

    def add_k8s_client(self, controller: Bundle, agent: Bundle) -> None:
        # TODO first check/validate if possible to combine target and client (ie. check if both are k8s backends, no services, etc)
        token = controller.server.get_kubernetes_token()
        url = f"https://{controller.server.ip}:6443"
        agent.server.install_kubernetes(controller_url=url, controller_token=token)
        controller.cluster.append(agent.server)
        self.delete_bundle(agent)

    def remove_k8s_client(self, controller: Bundle, agent: AbstractServer) -> Bundle:
        # TODO first check/validate if possible to combine target and client (ie. check if both are k8s backends, no services, etc)
        bundle = Bundle(name=agent.ip, server=agent)
        self.bundles.append(bundle)
        controller.cluster.remove(agent)
        return bundle

    @classmethod
    def load_server_config(cls, filepath: str, password: str) -> Bundle:
        server_dict = load_from_json(filepath, password)
        server = dict_to_dataclass(server_dict, [AbstractServer])
        return Bundle(name=server.ip, server=server)

    def save(self, filepath: str, password: str) -> None:
        infra_dict = dataclass_to_dict(self)
        save_to_json(infra_dict, filepath, password, encrypt=True)

    @classmethod
    def load(cls, filepath: str, password: str) -> "Infrastructure":
        infra_dict = load_from_json(filepath, password, encrypted=True)
        return dict_to_dataclass(infra_dict, hooks=[AbstractServer, AbstractService])
