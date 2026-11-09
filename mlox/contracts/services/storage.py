"""Service capability contracts."""

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, ClassVar
from .capabilities import ServiceCapability
if TYPE_CHECKING:
    from mlox.infra import Infrastructure
    from mlox.object_storage import AbstractObjectStorageClient


class AbstractObjectStorageService(ABC):
    """Service that provides a provider-neutral binary object-storage client."""

    capabilities: ClassVar[set[ServiceCapability]] = {ServiceCapability.OBJECT_STORAGE}

    @abstractmethod
    def get_storage(self, infra: "Infrastructure") -> "AbstractObjectStorageClient":
        """Return a client for listing, reading and writing objects."""


class AbstractS3ObjectStorageService(AbstractObjectStorageService):
    """Marker for object storage exposing an S3-compatible API."""

    capabilities: ClassVar[set[ServiceCapability]] = {
        ServiceCapability.OBJECT_STORAGE, ServiceCapability.S3_OBJECT_STORAGE,
    }
