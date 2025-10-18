"""
Singleton-based Service Registry (NO GLOBALS)
"""

from typing import Dict, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from mlox.service import AbstractService


class ServiceRegistrySingleton:
    """Thread-safe singleton for service registry"""

    _instance: Optional["ServiceRegistrySingleton"] = None
    _initialized: bool = False

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if not self._initialized:
            self._services: Dict[str, "AbstractService"] = {}
            ServiceRegistrySingleton._initialized = True

    def register_service(self, uuid: str, service: "AbstractService") -> None:
        """Register a service by UUID"""
        self._services[uuid] = service

    def get_service(self, uuid: str) -> Optional["AbstractService"]:
        """Get service by UUID"""
        return self._services.get(uuid)

    def unregister_service(self, uuid: str) -> None:
        """Remove service from registry"""
        self._services.pop(uuid, None)

    def clear(self) -> None:
        """Clear all services (useful for testing)"""
        self._services.clear()


# Convenience functions (no globals needed)
def get_service_registry() -> ServiceRegistrySingleton:
    """Get the singleton registry instance"""
    return ServiceRegistrySingleton()


def register_service(uuid: str, service: "AbstractService") -> None:
    """Register a service"""
    get_service_registry().register_service(uuid, service)


def get_dependent_service(uuid: str) -> Optional["AbstractService"]:
    """Get a dependent service by UUID"""
    return get_service_registry().get_service(uuid)
