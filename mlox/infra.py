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
"""

from abc import abstractmethod
from collections.abc import Generator
import logging

from datetime import datetime
from dataclasses import dataclass, field
from typing import Optional, List, Literal, Dict, Any

from mlox.config import (
    ServiceConfig,
)
from mlox.server import AbstractServer, ServerCapability
from mlox.service import AbstractService
from mlox.utils import (
    dataclass_to_dict,
    dict_to_dataclass,
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

    # -------------------------------------------------------------------------
    # Legacy compatibility wrappers around application-level infrastructure ops.
    # These methods remain on Infrastructure temporarily and will be removed
    # once callers use the application layer directly.

    def clear_service_registry(self) -> None:
        """Clear bound service lookups (legacy compatibility name)."""
        from mlox.application import infrastructure_ops as infra_use_cases

        infra_use_cases.clear_service_lookups(self)

    def remove_bundle(self, bundle: Bundle) -> None:
        from mlox.application import infrastructure_ops as infra_use_cases

        infra_use_cases.remove_bundle(self, bundle)
        return None

    def setup_service(self, service: AbstractService) -> None:
        from mlox.application import infrastructure_ops as infra_use_cases

        infra_use_cases.setup_service(self, service)

    def teardown_service(self, service: AbstractService) -> None:
        from mlox.application import infrastructure_ops as infra_use_cases

        infra_use_cases.teardown_service(self, service)

    def add_service(
        self,
        ip: str,
        config: ServiceConfig,
        params: Dict[str, Any],
        service: AbstractService | None = None,
    ) -> Bundle | None:
        from mlox.application import infrastructure_ops as infra_use_cases

        return infra_use_cases.add_service(self, ip, config, params, service=service)

    def get_service_config(
        self, service: AbstractService | AbstractServer
    ) -> ServiceConfig | None:
        from mlox.application import infrastructure_ops as infra_use_cases

        return infra_use_cases.get_service_config(self, service)

    def add_server(
        self, config: ServiceConfig, params: Dict[str, str]
    ) -> Bundle | None:
        from mlox.application import infrastructure_ops as infra_use_cases

        return infra_use_cases.add_server(self, config, params)

    def populate_service_registry(self) -> None:
        """Bind service lookup context to loaded services (legacy compatibility name)."""
        from mlox.application import infrastructure_ops as infra_use_cases

        infra_use_cases.populate_service_registry(self)

    def populate_configs(self) -> None:
        from mlox.application import infrastructure_ops as infra_use_cases

        infra_use_cases.populate_configs(self)
