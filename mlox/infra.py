"""Infrastructure domain models for bundles, services, and registry-aware composition.

Purpose:
- Represent and mutate project infrastructure state, including server bundles and configured services.

Key public classes/functions:
- ``Infrastructure`` for top-level infrastructure orchestration and serialization
- ``Bundle`` for grouping services by server

Expected runtime mode:
- Remote executor + CLI/UI/TUI backend state management

Related modules (plain-text links):
- mlox.server
- mlox.service
- mlox.config
- mlox.project
"""

from collections.abc import Generator
import logging

from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Literal, Optional

from mlox.config import ServiceConfig, load_all_service_configs, load_service_config_by_id
from mlox.server import AbstractServer, ServerCapability
from mlox.service import AbstractService

from mlox.utils import dataclass_to_dict, dict_to_dataclass

logger = logging.getLogger(__name__)


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
        self.hydrate_runtime()

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

    def filter_server_by_capability(
        self, capability: ServerCapability | str
    ) -> List[AbstractServer]:
        capability_value = (
            capability.value
            if isinstance(capability, ServerCapability)
            else str(capability).strip().lower()
        )
        servers: List[AbstractServer] = list()
        for bundle in self.bundles:
            server_capabilities = {
                c.value if isinstance(c, ServerCapability) else str(c).strip().lower()
                for c in getattr(bundle.server, "capabilities", set())
            }
            if capability_value in server_capabilities:
                servers.append(bundle.server)
        return servers

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

    def remove_bundle(self, bundle: Bundle) -> bool:
        """Remove a bundle from the infrastructure if it is present."""

        try:
            self.bundles.remove(bundle)
            return True
        except ValueError:
            logger.warning("Bundle %s was not present in infrastructure.", bundle.name)
            return False

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

    def get_service_by_name(self, service_name: str) -> AbstractService | None:
        return self.get_service(service_name)

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

    def list_kubernetes_controller(self) -> List[Bundle]:
        return [
            bundle
            for bundle in self.bundles
            if "kubernetes" in bundle.server.backend and bundle.server.state == "running"
        ]

    def filter_bundles_by_backend(
        self, backend: Literal["native", "docker", "kubernetes", "local", "connector"]
    ) -> List[Bundle]:
        return [b for b in self.bundles if backend in b.server.backend]

    def to_dict(self) -> Dict:
        infra_dict = dataclass_to_dict(self)
        _ = infra_dict.pop("configs", None)
        return infra_dict

    @classmethod
    def from_dict(
        cls,
        infra_dict: Dict,
        configs: Iterable[ServiceConfig] | None = None,
    ) -> "Infrastructure":
        infra = dict_to_dataclass(infra_dict, hooks=[AbstractServer, AbstractService])
        if configs is None:
            infra.hydrate_runtime()
        else:
            infra.hydrate_runtime(configs)
        return infra

    def get_service_config(
        self, service: AbstractService | AbstractServer
    ) -> ServiceConfig | None:
        if service.service_config_id in self.configs:
            return self.configs[service.service_config_id]
        config = load_service_config_by_id(service.service_config_id)
        if config:
            self.configs[service.service_config_id] = config
        return config

    def hydrate_runtime(
        self,
        configs: Iterable[ServiceConfig] | None = None,
    ) -> None:
        """Populate non-persistent config and service lookup state."""
        self.configs = {}
        catalog = list(configs) if configs is not None else load_all_service_configs(
            prefix="mlox"
        )
        if configs is None:
            catalog.extend(load_all_service_configs(prefix="mlox-server"))
        for config in catalog:
            self.configs[config.id] = config
        for service in self.services():
            service.bind_service_lookup(self)
