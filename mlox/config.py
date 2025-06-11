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
    module: str
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
    # This type hint correctly defines the desired final structure
    is_monitor: bool = False
    ports: Dict[str, int] = field(default_factory=dict)
    groups: Dict[str, Any] = field(default_factory=dict)
    ui: Dict[str, str] = field(default_factory=dict)
    build: Dict[str, BuildConfig] = field(default_factory=dict)

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

    def instantiate(
        self, build_key: str, params: Dict[str, str]
    ) -> Optional[AbstractService]:
        if build_key not in self.build:
            logging.error(f"Build key '{build_key}' not found in service config.")
            return None
        build_config = self.build[build_key]
        try:
            # Use details from the specific BuildConfig object
            module = importlib.import_module(build_config.module)
            service_class = getattr(module, build_config.class_name)

            if not issubclass(service_class, AbstractService):
                logging.error(
                    f"Class {build_config.class_name} from {build_config.module} is not a subclass of AbstractService."
                )
                return None

            init_params = dict()
            if build_config.params:
                init_params.update(build_config.params)
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
            logging.error(f"Error instantiating service {build_config.class_name}: {e}")
            return None
        except TypeError as e:
            logging.error(
                f"Error calling constructor for {build_config.class_name}: {e}. Check parameters: {init_params}"
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
            # Use details from the specific BuildConfig object
            module = importlib.import_module(self.build.module)
            service_class = getattr(module, self.build.class_name)

            print(service_class)
            if not issubclass(service_class, AbstractServer):
                logging.error(
                    f"Class {self.build.class_name} from {self.build.module} is not a subclass of AbstractServer."
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
                parsed_build_dict: Dict[str, BuildConfig] = {}

                if isinstance(raw_build_dict, dict):
                    for build_type, build_config_data in raw_build_dict.items():
                        if isinstance(build_config_data, dict):
                            try:
                                # Create BuildConfig instance from the nested dict
                                build_config_instance = BuildConfig(**build_config_data)
                                parsed_build_dict[build_type] = build_config_instance
                            except TypeError as e:
                                logging.error(
                                    f"Error creating BuildConfig for type '{build_type}' in {filepath}: {e}. Data: {build_config_data}"
                                )
                        else:
                            logging.warning(
                                f"Expected a dictionary for build type '{build_type}' in {filepath}, but got {type(build_config_data)}. Skipping."
                            )
                else:
                    logging.warning(
                        f"Expected 'build' key to contain a dictionary in {filepath}, but got {type(raw_build_dict)}. Ignoring build section."
                    )

                # Replace the raw build dictionary with the parsed one
                service_data["build"] = parsed_build_dict
                # --- End of Manual Parsing ---

                # Now instantiate ServiceConfig with the processed data
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


def test_service_configs():
    logging.basicConfig(level=logging.INFO)

    # Example: Assuming you have a stack config in ./stacks/airflow_3.0.0/mlox-config.yaml
    config_dir = "./stacks/airflow"
    service_configs = load_service_configs(config_dir)

    if service_configs:
        print(f"Loaded {len(service_configs)} service configuration(s).")
        first_config = service_configs[0]
        print(f"Service Name: {first_config.name}")
        print(f"Build configurations found: {list(first_config.build.keys())}")

        # Example of accessing a specific build config
        docker_build_config = first_config.build.get("docker")
        if docker_build_config:
            print(f"Docker Build Module: {docker_build_config.module}")
            print(f"Docker Build Class: {docker_build_config.class_name}")
            print(f"Docker Build Params: {docker_build_config.params}")
            print(
                f"Is instance of BuildConfig? {isinstance(docker_build_config, BuildConfig)}"
            )  # Should be True

        # Example instantiation
        params = {
            "${MLOX_USER}": "pups",
            "${MLOX_PORT}": "port22",
            "${MLOX_PW}": "dkjsajdlkfj",
        }
        instantiated_service = service_configs[0].instantiate("docker", params)
        if instantiated_service:
            print(f"Successfully instantiated service: {type(instantiated_service)}")
            print(instantiated_service)

    else:
        print("No service configurations loaded.")


if __name__ == "__main__":
    configs = load_all_service_configs("./stacks/")
    for c in configs:
        print(c.name + c.version)
