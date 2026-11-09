"""Server capability contracts."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Dict


@dataclass
class AbstractBackendServer(ABC):
    @abstractmethod
    def setup_backend(self) -> None:
        pass

    @abstractmethod
    def teardown_backend(self) -> None:
        pass

    @abstractmethod
    def get_backend_status(self) -> Dict[str, Any]:
        pass

    @abstractmethod
    def start_backend_runtime(self) -> None:
        pass

    @abstractmethod
    def stop_backend_runtime(self) -> None:
        pass


@dataclass
class AbstractNativeServer(AbstractBackendServer):
    pass


@dataclass
class AbstractDockerServer(AbstractBackendServer):
    pass


@dataclass
class AbstractKubernetesServer(AbstractBackendServer):
    pass


@dataclass
class AbstractLocalServer(AbstractBackendServer):
    pass


@dataclass
class AbstractConnectorServer(AbstractBackendServer):
    """Backend contract for virtual, externally hosted service connectors."""

    pass
