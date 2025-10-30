"""Private container registry service built on the official distribution image."""

__all__ = ["RegistryDockerService"]

from .docker import RegistryDockerService
