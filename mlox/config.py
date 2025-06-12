import importlib
import logging
import os
import yaml

from dataclasses import dataclass, field
from typing import Dict, List, Any, Optional, Callable

from mlox.service import AbstractService
from mlox.server import AbstractServer


@dataclass
class BuildConfig:
    class_name: str
    params: Dict[str, Any] | None = field(default_factory=dict)


@dataclass
class ServiceConfig:
    name: str
    version: str
    maintainer: str
    description: str
    description_short: str
    links: Dict[str, str]
    requirements: Dict[str, float]
    build: BuildConfig
    # This type hint correctly defines the desired final structure
    ports: Dict[str, int] = field(default_factory=dict)
    groups: Dict[str, Any] = field(default_factory=dict)
    ui: Dict[str, str] = field(default_factory=dict)

    def instantiate_ui(self, func_name: str) -> Callable | None:
        if func_name not in self.ui:
            # This is normal behavior
            return None
        try:
            # Split the string into module path and function name
            module_path, func_name = self.ui[func_name].rsplit(".", 1)
            # Import the module
            module = importlib.import_module(module_path)
            # Get the function object
            callable_settings_func = getattr(module, func_name)
            return callable_settings_func
        except (ImportError, AttributeError) as e:
            logging.error(
                f"Could not load callable {func_name} for this service {self.name}: {e}"
            )
        except Exception as e:
            logging.error(
                f"An error occurred while getting the callable {func_name}: {e}"
            )
        return None

    def instantiate_build(self, params: Dict[str, str]) -> AbstractService | None:
        try:
            # Split the string into module path and function name
            module_path, class_name = self.build.class_name.rsplit(".", 1)

            # Use details from the specific BuildConfig object
            module = importlib.import_module(module_path)
            service_class = getattr(module, class_name)

            if not issubclass(service_class, AbstractService):
                logging.error(
                    f"Class {class_name} from {module_path} is not a subclass of AbstractService."
                )
                return None

            init_params = dict()
            if self.build.params:
                init_params.update(self.build.params)
            for key, value in init_params.items():
                for k in params.keys():
                    if k in value:
                        init_params[key] = value.replace(k, params[k])

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


@dataclass
class ServerConfig:
    name: str
    versions: List[str | float]
    maintainer: str
    description: str
    links: Dict[str, str]
    build: BuildConfig

    def instantiate(
        self, params: Dict[str, str], init_params: Dict[str, str] = dict()
    ) -> Optional[AbstractServer]:
        try:
            # Split the string into module path and function name
            module_path, class_name = self.build.class_name.rsplit(".", 1)

            # Use details from the specific BuildConfig object
            module = importlib.import_module(module_path)
            service_class = getattr(module, class_name)

            print(service_class)
            if not issubclass(service_class, AbstractServer):
                logging.error(
                    f"Class {class_name} from {module_path} is not a subclass of AbstractServer."
                )
                return None

            if self.build.params:
                init_params.update(self.build.params)
            for key, value in init_params.items():
                for k in params.keys():
                    if k in value:
                        init_params[key] = value.replace(k, params[k])

            # Pass the server instance and combined parameters
            service_instance = service_class(
                **init_params
            )  # Assuming service class __init__ takes only its specific params
            return service_instance

        except (ImportError, AttributeError) as e:
            logging.error(f"Error instantiating service {self.build.class_name}: {e}")
            print(self.build)
            return None
        except TypeError as e:
            logging.error(
                f"Error calling constructor for {self.build.class_name}: {e}. Check parameters: {init_params}"
            )
            return None


def load_all_server_configs(root_dir: str) -> List[ServerConfig]:
    configs: List[ServerConfig] = []
    if not os.path.isdir(root_dir):
        logging.error(f"Configuration directory not found: {root_dir}")
        return configs

    candidates = os.listdir(root_dir)
    for candidate in candidates:
        configs.extend(load_server_configs(root_dir + "/" + candidate))
    return configs


def load_all_service_configs(root_dir: str) -> List[ServiceConfig]:
    configs: List[ServiceConfig] = []
    if not os.path.isdir(root_dir):
        logging.error(f"Configuration directory not found: {root_dir}")
        return configs

    candidates = os.listdir(root_dir)
    for candidate in candidates:
        configs.extend(load_service_configs(root_dir + "/" + candidate))
    return configs


def load_server_configs(config_dir: str) -> List[ServerConfig]:
    """Loads service configurations from YAML files in the given directory."""
    configs: List[ServerConfig] = []
    if not os.path.isdir(config_dir):
        logging.error(f"Configuration directory not found: {config_dir}")
        return configs

    # Look for mlox-config.yaml specifically within the provided directory
    candidates = os.listdir(config_dir)
    for candidate in candidates:
        filepath = f"{config_dir}/{candidate}"
        if not (
            os.path.isfile(filepath)
            and candidate.startswith("mlox-server.")
            and candidate.endswith(".yaml")
        ):
            continue
        logging.info(f"Loading service config from: {filepath}")
        with open(filepath, "r") as f:
            try:
                service_data = yaml.safe_load(f)
                if not isinstance(service_data, dict):
                    logging.error(
                        f"Invalid format in {filepath}. Expected a dictionary at the top level."
                    )
                    return configs  # Or continue if loading multiple files

                raw_build_dict = service_data.get("build", {})
                service_data["build"] = BuildConfig(**raw_build_dict)
                configs.append(ServerConfig(**service_data))

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

    return configs


def load_service_configs(config_dir: str) -> List[ServiceConfig]:
    """Loads service configurations from YAML files in the given directory."""
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
            and candidate.startswith("mlox.")
            and candidate.endswith(".yaml")
        ):
            continue
        logging.info(f"Loading service config from: {filepath}")
        with open(filepath, "r") as f:
            try:
                service_data = yaml.safe_load(f)
                if not isinstance(service_data, dict):
                    logging.error(
                        f"Invalid format in {filepath}. Expected a dictionary at the top level."
                    )
                    return configs  # Or continue if loading multiple files

                # --- Manual Parsing of the 'build' dictionary ---
                raw_build_dict = service_data.get("build", {})
                service_data["build"] = BuildConfig(**raw_build_dict)
                configs.append(ServiceConfig(**service_data))

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

    return configs


if __name__ == "__main__":
    configs = load_all_service_configs("./stacks/")
    for c in configs:
        print(c.name + c.version)
