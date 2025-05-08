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
    backend: Literal["docker", "kubernetes"] = field(default="docker")
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


@dataclass
class Infrastructure:
    bundles: List[Bundle] = field(default_factory=list, init=False)

    def get_bundle_by_ip(self, ip: str) -> Optional[Bundle]:
        for bundle in self.bundles:
            if bundle.server.ip == ip:
                return bundle
        return None

    def load_server_config(self, filepath: str, password: str) -> Bundle:
        server_dict = load_from_json(filepath, password)
        server = dict_to_dataclass(server_dict, [AbstractServer])
        self.bundles.append(Bundle(name=server.ip, server=server))
        return self.bundles[-1]

    def save(self, filepath: str, password: str) -> None:
        infra_dict = dataclass_to_dict(self)
        save_to_json(infra_dict, filepath, password, encrypt=True)

    @classmethod
    def load(cls, filepath: str, password: str) -> "Infrastructure":
        infra_dict = load_from_json(filepath, password, encrypted=True)
        return dict_to_dataclass(infra_dict, hooks=[AbstractServer, AbstractService])
