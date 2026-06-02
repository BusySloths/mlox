import os
import yaml
import logging
import importlib

from importlib import resources, metadata as importlib_metadata
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Literal, TypedDict

from mlox.service import (
    AbstractModelRegistryService,
    AbstractModelServerService,
    AbstractRepositoryService,
    AbstractSecretManagerService,
    AbstractService,
    ServiceCapability,
)
from mlox.server import (
    AbstractDockerServer,
    AbstractFirewallServer,
    AbstractGitServer,
    AbstractInitialPasswordAuthServer,
    AbstractKubernetesServer,
    AbstractLocalServer,
    AbstractNativeServer,
    AbstractServer,
    ServerCapability,
)

from mlox.ui.registry import get_handler

PluginKind = Literal["service", "server"]


SERVER_CAPABILITY_ABCS = {
    ServerCapability.GIT.value: AbstractGitServer,
    ServerCapability.FIREWALL.value: AbstractFirewallServer,
    ServerCapability.INITIAL_AUTH_PASSWORD.value: AbstractInitialPasswordAuthServer,
    ServerCapability.NATIVE.value: AbstractNativeServer,
    ServerCapability.DOCKER.value: AbstractDockerServer,
    ServerCapability.KUBERNETES.value: AbstractKubernetesServer,
    ServerCapability.LOCAL.value: AbstractLocalServer,
}


SERVICE_CAPABILITY_ABCS = {
    ServiceCapability.SECRET_MANAGER.value: AbstractSecretManagerService,
    ServiceCapability.REPOSITORY.value: AbstractRepositoryService,
    ServiceCapability.MODEL_REGISTRY.value: AbstractModelRegistryService,
    ServiceCapability.MODEL_SERVER.value: AbstractModelServerService,
}

SERVICE_GROUP_ALIASES = {
    "secret_manager": ServiceCapability.SECRET_MANAGER.value,
    "repository": ServiceCapability.REPOSITORY.value,
    "git": ServiceCapability.REPOSITORY.value,
    "model_registry": ServiceCapability.MODEL_REGISTRY.value,
    "model_server": ServiceCapability.MODEL_SERVER.value,
    "observability": ServiceCapability.OBSERVABILITY.value,
    "data_warehouse": ServiceCapability.DATA_WAREHOUSE.value,
    "object_storage": ServiceCapability.OBJECT_STORAGE.value,
    "spreadsheet": ServiceCapability.SPREADSHEET.value,
    "database": ServiceCapability.DATABASE.value,
    "vector_database": ServiceCapability.VECTOR_DATABASE.value,
    "cache": ServiceCapability.CACHE.value,
    "message_broker": ServiceCapability.MESSAGE_BROKER.value,
    "workflow_orchestrator": ServiceCapability.WORKFLOW_ORCHESTRATOR.value,
    "feature_store": ServiceCapability.FEATURE_STORE.value,
    "container_registry": ServiceCapability.CONTAINER_REGISTRY.value,
    "deployment": ServiceCapability.DEPLOYMENT.value,
    "llm": ServiceCapability.LLM.value,
    "dashboard": ServiceCapability.DASHBOARD.value,
}


def _normalize_capability_name(value: Any) -> str:
    if isinstance(value, (ServerCapability, ServiceCapability)):
        return value.value
    return str(value).strip().lower().replace("-", "_")


def _normalize_capability_values(value: Any) -> set[str]:
    if value is None:
        return set()
    if isinstance(value, dict):
        return {_normalize_capability_name(key) for key in value.keys()}
    if isinstance(value, (list, tuple, set)):
        return {_normalize_capability_name(item) for item in value}
    return {_normalize_capability_name(value)}


def _normalize_capability_map(capabilities: Dict[str, Any]) -> Dict[str, set[str]]:
    normalized: Dict[str, set[str]] = {}
    for section, values in capabilities.items():
        section_name = str(section).strip().lower()
        normalized[section_name] = _normalize_capability_values(values)
    return normalized


def _capabilities_from_groups(groups: Dict[str, Any]) -> Dict[str, set[str]]:
    derived: Dict[str, set[str]] = {"server": set(), "backend": set(), "service": set()}

    server_groups = groups.get("server")
    if isinstance(server_groups, dict):
        derived["server"].update(_normalize_capability_values(server_groups))

    backend_groups = groups.get("backend")
    if isinstance(backend_groups, dict):
        for backend in backend_groups.keys():
            derived["backend"].add(_normalize_capability_name(backend))

    for group in groups.keys():
        group_name = _normalize_capability_name(group)
        capability = SERVICE_GROUP_ALIASES.get(group_name)
        if capability:
            derived["service"].add(capability)

    return {section: values for section, values in derived.items() if values}


def _load_build_class(config: "ServiceConfig") -> type | None:
    try:
        module_path, class_name = config.build.class_name.rsplit(".", 1)
        module = importlib.import_module(module_path)
        build_class = getattr(module, class_name)
    except (ImportError, AttributeError, ValueError) as exc:
        logging.warning(
            "Could not load build class %s for capability validation: %s",
            config.build.class_name,
            exc,
        )
        return None
    return build_class


def _class_capabilities(build_class: type) -> set[str]:
    return {
        _normalize_capability_name(capability)
        for capability in getattr(build_class, "capabilities", set())
    }


def _server_class_capabilities(server_class: type) -> set[str]:
    return _class_capabilities(server_class)


def _service_class_capabilities(service_class: type) -> set[str]:
    return _class_capabilities(service_class)


def _validate_server_config_capabilities(config: "ServiceConfig") -> None:
    server_class = _load_build_class(config)
    if server_class is None:
        return
    if not isinstance(server_class, type) or not issubclass(
        server_class, AbstractServer
    ):
        return

    declared = config.server_capabilities() | config.backend_capabilities()
    known = {capability.value for capability in ServerCapability}
    unknown = declared - known
    if unknown:
        logging.warning(
            "Server config %s declares unknown capabilities: %s",
            config.id,
            sorted(unknown),
        )

    declared_known = declared & known
    class_capabilities = _server_class_capabilities(server_class)

    missing_from_class = declared_known - class_capabilities
    if missing_from_class:
        logging.warning(
            "Server config %s declares capabilities not supported by %s: %s",
            config.id,
            server_class.__name__,
            sorted(missing_from_class),
        )

    missing_from_config = class_capabilities - declared_known
    if missing_from_config:
        logging.warning(
            "Server class %s supports capabilities not advertised by config %s: %s",
            server_class.__name__,
            config.id,
            sorted(missing_from_config),
        )

    for capability in sorted(declared_known):
        required_abc = SERVER_CAPABILITY_ABCS.get(capability)
        if required_abc and not issubclass(server_class, required_abc):
            logging.warning(
                "Server config %s declares capability %s but %s does not implement %s",
                config.id,
                capability,
                server_class.__name__,
                required_abc.__name__,
            )


def _validate_service_config_capabilities(config: "ServiceConfig") -> None:
    service_class = _load_build_class(config)
    if service_class is None:
        return
    if not isinstance(service_class, type) or not issubclass(
        service_class, AbstractService
    ):
        return

    declared = config.service_capabilities()
    known = {capability.value for capability in ServiceCapability}
    unknown = declared - known
    if unknown:
        logging.warning(
            "Service config %s declares unknown service capabilities: %s",
            config.id,
            sorted(unknown),
        )

    declared_known = declared & known
    class_capabilities = _service_class_capabilities(service_class)
    class_service_capabilities = class_capabilities & known

    missing_from_class = declared_known - class_service_capabilities
    if missing_from_class:
        logging.warning(
            "Service config %s declares service capabilities not supported by %s: %s",
            config.id,
            service_class.__name__,
            sorted(missing_from_class),
        )

    missing_from_config = class_service_capabilities - declared_known
    if missing_from_config:
        logging.warning(
            "Service class %s supports service capabilities not advertised by config %s: %s",
            service_class.__name__,
            config.id,
            sorted(missing_from_config),
        )

    for capability in sorted(declared_known):
        required_abc = SERVICE_CAPABILITY_ABCS.get(capability)
        if required_abc and not issubclass(service_class, required_abc):
            logging.warning(
                "Service config %s declares capability %s but %s does not implement %s",
                config.id,
                capability,
                service_class.__name__,
                required_abc.__name__,
            )


@dataclass
class BuildConfig:
    class_name: str
    params: Dict[str, Any] | None = field(default_factory=dict)


@dataclass
class ServiceConfig:
    id: str
    name: str
    version: str | float | int
    maintainer: str
    description: str
    description_short: str
    links: Dict[str, str]
    build: BuildConfig
    groups: Dict[str, Any] = field(default_factory=dict)
    capabilities: Dict[str, list[str]] = field(default_factory=dict)
    requirements: Dict[str, float] = field(default_factory=dict)
    ports: Dict[str, int] = field(default_factory=dict)
    path: str = field(default="", init=False)

    def declared_capabilities(self) -> Dict[str, set[str]]:
        if self.capabilities:
            return _normalize_capability_map(self.capabilities)
        return _capabilities_from_groups(self.groups)

    def server_capabilities(self) -> set[str]:
        return self.declared_capabilities().get("server", set())

    def backend_capabilities(self) -> set[str]:
        return self.declared_capabilities().get("backend", set())

    def service_capabilities(self) -> set[str]:
        return self.declared_capabilities().get("service", set())

    def get_ui_handler(self, frontend: str, function_name: str) -> Callable | None:
        return get_handler(
            config_id=self.id,
            frontend=frontend,
            function_name=function_name,
        )

    def instantiate_server(self, params: Dict[str, Any]) -> AbstractServer | None:
        res = self.instantiate_build(params)
        if res and isinstance(res, AbstractServer):
            return res
        return None

    def instantiate_service(self, params: Dict[str, Any]) -> AbstractService | None:
        res = self.instantiate_build(params)
        if res and isinstance(res, AbstractService):
            return res
        return None

    def instantiate_build(
        self, params: Dict[str, Any]
    ) -> AbstractServer | AbstractService | None:
        try:
            # Split the string into module path and function name
            module_path, class_name = self.build.class_name.rsplit(".", 1)
            module = importlib.import_module(module_path)
            service_class = getattr(module, class_name)
            if not issubclass(service_class, AbstractService) and not issubclass(
                service_class, AbstractServer
            ):
                logging.error(
                    f"Class {class_name} from {module_path} is not a subclass of AbstractService/AbstractServer."
                )
                return None

            init_params = {"service_config_id": self.id}
            if self.build.params:
                init_params.update(self.build.params)
            for key, value in init_params.items():
                for k in params.keys():
                    if k in value:
                        # Two cases:
                        # 1. value contains exactly k -> value does not need to be a string type
                        # 2. value is a string that contains k maybe even multiple times
                        if len(value) == len(k):
                            init_params[key] = params[k]
                        else:
                            init_params[key] = init_params[key].replace(k, params[k])

            # Pass the server instance and combined parameters
            service_instance = service_class(**init_params)
            return service_instance

        except (ImportError, AttributeError) as e:
            logging.error(f"Error instantiating service {self.build.class_name}: {e}")
            return None
        except TypeError as e:
            logging.error(
                f"Error calling constructor for {self.build.class_name}: {e}. Check parameters: {init_params}"
            )
            return None


class ConfigPluginRecord(TypedDict):
    """Plugin discovery record with an instantiated ``ServiceConfig`` object."""

    plugin_id: str
    config: ServiceConfig


def get_stacks_path(prefix: Literal["mlox", "mlox-server"] = "mlox") -> str:
    """Return the on-disk path for bundled configuration assets.

    Service configurations now live alongside their implementation modules
    under ``mlox.services`` while server configurations are colocated within
    ``mlox.servers``.  This helper keeps backward compatibility with the
    previous single "stacks" directory by routing calls based on the
    configuration prefix.
    """

    package = "mlox.services" if prefix == "mlox" else "mlox.servers"
    return str(resources.files(package))


def load_service_config_by_id(service_id: str) -> ServiceConfig | None:
    # for service configs
    for config in load_all_service_configs(prefix="mlox"):
        if config.id == service_id:
            return config
    # for all server configs
    for config in load_all_service_configs(prefix="mlox-server"):
        if config.id == service_id:
            return config
    return None


def _load_builtin_configs(
    prefix: Literal["mlox", "mlox-server"] = "mlox",
) -> List[ServiceConfig]:
    root_dir = get_stacks_path(prefix)

    configs: List[ServiceConfig] = []
    if not os.path.isdir(root_dir):
        logging.error(f"Configuration directory not found: {root_dir}")
        return configs

    candidates = os.listdir(root_dir)
    for candidate in candidates:
        if not os.path.isdir(os.path.join(root_dir, candidate)):
            continue
        configs.extend(load_service_configs(root_dir, candidate, prefix=prefix))
    return configs


def load_all_server_configs(*, include_plugins: bool = True) -> List[ServiceConfig]:
    return load_all_service_configs(
        prefix="mlox-server", include_plugins=include_plugins
    )


def load_all_service_configs(
    prefix: Literal["mlox", "mlox-server"] = "mlox",
    *,
    include_plugins: bool = True,
) -> List[ServiceConfig]:
    configs = _load_builtin_configs(prefix=prefix)
    if not include_plugins:
        return configs

    kind: PluginKind = "service" if prefix == "mlox" else "server"
    for plugin in _discover_entrypoint_plugins(kind):
        configs.append(plugin["config"])
    return configs


def load_service_configs(
    root_dir: str, service_dir: str, prefix: Literal["mlox", "mlox-server"]
) -> List[ServiceConfig]:
    """Loads service configurations from YAML files in the given directory."""
    config_dir = f"{root_dir}/{service_dir}"
    configs: List[ServiceConfig] = []
    if not os.path.isdir(config_dir):
        logging.info(f"Configuration directory not found: {config_dir}")
        return configs

    # Look for mlox-config.yaml specifically within the provided directory
    candidates = os.listdir(config_dir)
    for candidate in candidates:
        filepath = f"{config_dir}/{candidate}"
        if not (
            os.path.isfile(filepath)
            and candidate.startswith(prefix + ".")
            and candidate.endswith(".yaml")
        ):
            continue
        logging.debug(f"Loading service config from: {filepath}")
        config = load_config(root_dir, service_dir, candidate)
        if config:
            configs.append(config)
    return configs


def load_config(
    root_dir: str, service_dir: str, candidate: str
) -> ServiceConfig | None:
    filepath = f"{root_dir}/{service_dir}/{candidate}"
    with open(filepath, "r") as f:
        try:
            service_data = yaml.safe_load(f)
            if not isinstance(service_data, dict):
                logging.error(
                    f"Invalid format in {filepath}. Expected a dictionary at the top level."
                )
                return None

            # --- Manual Parsing of the 'build' dictionary ---
            raw_build_dict = service_data.get("build", {})
            service_data["build"] = BuildConfig(**raw_build_dict)
            service_config_instance = ServiceConfig(**service_data)
            service_config_instance.path = f"{service_dir}/{candidate}"
            if candidate.startswith("mlox-server."):
                _validate_server_config_capabilities(service_config_instance)
            else:
                _validate_service_config_capabilities(service_config_instance)
            return service_config_instance

        except yaml.YAMLError as e:
            logging.error(f"Error parsing YAML file {filepath}: {e}")
        except TypeError as e:
            logging.error(
                (
                    f"Error initializing ServiceConfig from {filepath}: {e}. "
                    "Check if all required fields are present and correctly structured in the YAML. "
                    f"Data: {service_data}"
                )
            )
        except Exception as e:  # Catch other potential errors
            logging.error(
                f"An unexpected error occurred while processing {filepath}: {e}"
            )
    return None


def _entrypoint_group(kind: PluginKind) -> str:
    return "mlox.service_plugins" if kind == "service" else "mlox.server_plugins"


def _config_prefix(kind: PluginKind) -> str:
    return "mlox" if kind == "service" else "mlox-server"


def _from_entry_point(value: object) -> ConfigPluginRecord | None:
    if isinstance(value, ServiceConfig):
        return {"plugin_id": value.id, "config": value}
    return None


def _discover_entrypoint_plugins(kind: PluginKind) -> List[ConfigPluginRecord]:
    plugins: List[ConfigPluginRecord] = []
    eps = importlib_metadata.entry_points()
    for entry_point in eps.select(group=_entrypoint_group(kind)):
        try:
            provider = entry_point.load()
            provided = provider() if callable(provider) else provider
            plugin = _from_entry_point(provided)
            if plugin:
                plugins.append(plugin)
        except Exception:
            continue
    return plugins


def discover_config_plugins(kind: PluginKind) -> List[ConfigPluginRecord]:
    """Discover built-in and entry-point provided config plugins."""

    plugins: List[ConfigPluginRecord] = [
        {"plugin_id": config.id, "config": config}
        for config in _load_builtin_configs(prefix=_config_prefix(kind))
    ]
    plugins.extend(_discover_entrypoint_plugins(kind))
    return plugins


def discover_service_plugins() -> List[ConfigPluginRecord]:
    return discover_config_plugins("service")


def discover_server_plugins() -> List[ConfigPluginRecord]:
    return discover_config_plugins("server")


def resource_files():
    # The .files() API returns a traversable object for your package's data
    # This is the modern way (Python 3.9+) to access package resources.
    airflow_stack_path_obj = resources.files("mlox.services.airflow")
    # print(str(airflow_stack_path_obj))

    # You can join paths to get to a specific file
    compose_file_ref = airflow_stack_path_obj.joinpath(
        "docker-compose-airflow-2.9.2.yaml"
    )

    # To get a usable file system path, use the as_file() context manager.
    # This handles cases where the package is installed as a zip file.
    with resources.as_file(compose_file_ref) as compose_file_path:
        print(f"The path to the compose file is: {compose_file_path}")
        # Now you can use `compose_file_path` with other tools, e.g., to read it
        # with open(compose_file_path, "r") as f:
        #     content = f.read()


if __name__ == "__main__":
    # resource_files()
    # configs = load_all_service_configs()
    configs = load_all_server_configs()
    for c in configs:
        print(
            c.name
            + " "
            + str(c.version)
            + " "
            + str(list(c.groups.get("backend", {}).keys()))
            + " "
            + c.path
        )
