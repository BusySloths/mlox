"""Secret-manager adapters and descriptors used by a project workspace."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Dict

from mlox.project.repository import SqlCipherRepository
from mlox.secret_manager import AbstractSecretManager


class SecretManagerUnavailableError(RuntimeError):
    """Raised when the selected secret manager cannot be used."""


@dataclass(frozen=True)
class SecretManagerDescriptor:
    id: str
    name: str
    kind: str
    service_uuid: str | None
    is_active: bool
    is_available: bool | None
    supports_keyfile_export: bool
    manager: AbstractSecretManager | None
    service: Any | None = None


class EmbeddedSecretManager(AbstractSecretManager):
    def __init__(self, repository: SqlCipherRepository):
        self._repository = repository

    def is_working(self) -> bool:
        try:
            return self._repository.integrity_check()
        except Exception:
            return False

    def list_secrets(self, keys_only: bool = False) -> Dict[str, Any]:
        return self._repository.list_secrets(keys_only)

    def save_secret(self, name: str, my_secret: Dict | str) -> None:
        self._repository.save_secret(name, my_secret)

    def load_secret(self, name: str) -> Dict | str | None:
        return self._repository.load_secret(name)

    @classmethod
    def instantiate_secret_manager(cls, info: Dict[str, Any]):
        return None

    def get_access_secrets(self) -> Dict[str, Any] | None:
        return {"kind": "project", "location": str(self._repository.path)}


class UnavailableSecretManager(AbstractSecretManager):
    def __init__(self, service_uuid: str, reason: str):
        self.service_uuid = service_uuid
        self.reason = reason

    def _raise(self):
        raise SecretManagerUnavailableError(self.reason)

    def is_working(self) -> bool:
        return False

    def list_secrets(self, keys_only: bool = False) -> Dict[str, Any]:
        self._raise()

    def save_secret(self, name: str, my_secret: Dict | str) -> None:
        self._raise()

    def load_secret(self, name: str) -> Dict | str | None:
        self._raise()

    @classmethod
    def instantiate_secret_manager(cls, info: Dict[str, Any]):
        return None

    def get_access_secrets(self) -> Dict[str, Any] | None:
        self._raise()
