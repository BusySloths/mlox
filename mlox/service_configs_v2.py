import importlib
import logging
import os
import yaml
from dataclasses import dataclass, field
from typing import Dict, Type, List, Any, Optional
from abc import ABC, abstractmethod

from mlox.configs import AbstractService, Server, Infrastructure

# ... (Existing code from configs.py, including AbstractService, Server, etc.) ...


@dataclass
class ServiceConfig:
    name: str
    module: str
    class_name: str
    params: Dict[str, Any]


def load_service_configs(config_dir: str) -> List[ServiceConfig]:
    """Loads service configurations from YAML files in the given directory."""
    configs = []
    for filename in os.listdir(config_dir):
        if filename.endswith(".yaml"):
            filepath = os.path.join(config_dir, filename)
            with open(filepath, "r") as f:
                try:
                    data = yaml.safe_load(f)
                    for service_data in data.get(
                        "services", []
                    ):  # Assuming YAML has a 'services' key
                        configs.append(
                            ServiceConfig(
                                name=service_data["name"],
                                module=service_data[
                                    "module"
                                ],  # e.g., "mlox.services.mlflow"
                                class_name=service_data["class_name"],  # e.g., "MLFlow"
                                params=service_data.get("params", {}),
                            )
                        )
                except yaml.YAMLError as e:
                    logging.error(f"Error parsing YAML file {filepath}: {e}")
    return configs


def instantiate_service(
    config: ServiceConfig, server: Server
) -> Optional[AbstractService]:
    """Instantiates a service class from its configuration."""
    try:
        module = importlib.import_module(config.module)
        service_class = getattr(module, config.class_name)
        if not issubclass(service_class, AbstractService):
            logging.error(
                f"Class {config.class_name} from {config.module} is not a subclass of AbstractService."
            )
            return None
        # Handle parameters passed to the class's __init__ method
        service_instance = service_class(server=server, **config.params)
        return service_instance

    except (ImportError, AttributeError) as e:
        logging.error(f"Error instantiating service {config.name}: {e}")
        return None


class InfrastructureV2(Infrastructure):
    # ... (Existing code) ...

    def load_services(self, config_dir: str) -> None:
        """Loads and instantiates services from YAML configuration files."""
        for server in self.servers:
            configs = load_service_configs(config_dir)  # Use correct config directory
            for config in configs:
                service = instantiate_service(config, server)
                if service:
                    server.add_service(service)
