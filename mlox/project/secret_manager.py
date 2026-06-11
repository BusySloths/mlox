"""Compatibility secret-manager adapter backed by the encrypted project file."""
from __future__ import annotations
from typing import Any, Dict
from mlox.project.store import ProjectDatabase
from mlox.secret_manager import AbstractSecretManager


class ProjectSecretManager(AbstractSecretManager):
    def __init__(self, store: ProjectDatabase):
        self.store = store

    def is_working(self) -> bool:
        try:
            return self.store.integrity_check()
        except Exception:
            return False

    def list_secrets(self, keys_only: bool = False) -> Dict[str, Any]:
        return self.store.list_secrets(keys_only)

    def save_secret(self, name: str, my_secret: Dict | str) -> None:
        self.store.save_secret(name, my_secret)

    def load_secret(self, name: str) -> Dict | str | None:
        return self.store.load_secret(name)

    @classmethod
    def instantiate_secret_manager(cls, info: Dict[str, Any]):
        return None

    def get_access_secrets(self) -> Dict[str, Any] | None:
        return {"kind": "project", "location": str(self.store.path)}
