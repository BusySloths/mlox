import importlib
import logging
import os
import yaml

from dataclasses import dataclass, field
from typing import Dict, List, Any, Literal, Callable

from mlox.service import AbstractService
from mlox.server import AbstractServer

CONFIG_ROOT_DIR = "./stacks"


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
    ui: Dict[str, str] = field(default_factory=dict)
    requirements: Dict[str, float] = field(default_factory=dict)
    ports: Dict[str, int] = field(default_factory=dict)
    path: str = field(default="", init=False)

    def instantiate_ui(self, func_name: str) -> Callable | None:
        if func_name not in self.ui:
            # This is normal behavior
            return None
        callable_settings_func = None
        try:
            # Split the string into module path and function name
            module_path, func_name = self.ui[func_name].rsplit(".", 1)
            module = importlib.import_module(module_path)
            callable_settings_func = getattr(module, func_name)
        except (ImportError, AttributeError) as e:
            logging.error(f"Could not load callable {func_name} for {self.name}: {e}")
        except Exception as e:
            logging.error(
                f"An error occurred while getting the callable {func_name} for {self.name}: {e}"
            )
        return callable_settings_func

    def instantiate_server(self, params: Dict[str, str]) -> AbstractServer | None:
        res = self.instantiate_build(params)
        if res and isinstance(res, AbstractServer):
            return res
        return None

    def instantiate_service(self, params: Dict[str, str]) -> AbstractService | None:
        res = self.instantiate_build(params)
        if res and isinstance(res, AbstractService):
            return res
        return None

    def instantiate_build(
        self, params: Dict[str, str]
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


def load_all_server_configs(root_dir: str) -> List[ServiceConfig]:
    return load_all_service_configs(root_dir, prefix="mlox-server")


def load_all_service_configs(
    root_dir: str, prefix: Literal["mlox", "mlox-server"] = "mlox"
) -> List[ServiceConfig]:
    configs: List[ServiceConfig] = []
    if not os.path.isdir(root_dir):
        logging.error(f"Configuration directory not found: {root_dir}")
        return configs

    candidates = os.listdir(root_dir)
    for candidate in candidates:
        configs.extend(load_service_configs(root_dir, candidate, prefix=prefix))
    return configs


def load_service_config_by_id(root_dir: str, service_id: str) -> ServiceConfig | None:
    # for service configs
    for config in load_all_service_configs(root_dir, prefix="mlox"):
        if config.id == service_id:
            return config
    # for all server configs
    for config in load_all_service_configs(root_dir, prefix="mlox-server"):
        if config.id == service_id:
            return config
    return None


def load_service_configs(
    root_dir: str, service_dir: str, prefix: Literal["mlox", "mlox-server"]
) -> List[ServiceConfig]:
    """Loads service configurations from YAML files in the given directory."""
    config_dir = f"{root_dir}/{service_dir}"
    configs: List[ServiceConfig] = []
    if not os.path.isdir(config_dir):
        logging.error(f"Configuration directory not found: {config_dir}")
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
            return service_config_instance

        except yaml.YAMLError as e:
            logging.error(f"Error parsing YAML file {filepath}: {e}")
        except TypeError as e:
            logging.error(
                f"Error initializing ServiceConfig from {filepath}: {e}. Check if all required fields are present and correctly structured in the YAML. Data: {service_data}"
            )
        except Exception as e:  # Catch other potential errors
            logging.error(
                f"An unexpected error occurred while processing {filepath}: {e}"
            )
    return None


if __name__ == "__main__":
    configs = load_all_service_configs(CONFIG_ROOT_DIR)
    # configs = load_all_server_configs("./stacks")
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
