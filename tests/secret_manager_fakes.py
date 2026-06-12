from __future__ import annotations

from typing import Any, Dict

from mlox.secret_manager import AbstractSecretManager


class SerializableSecretManager(AbstractSecretManager):
    def __init__(self, secrets: Dict[str, Any] | None = None):
        self._store = dict(secrets or {})

    def is_working(self) -> bool:
        return True

    def list_secrets(self, keys_only: bool = False) -> Dict[str, Any]:
        if keys_only:
            return {name: None for name in self._store}
        return dict(self._store)

    def save_secret(self, name: str, my_secret: Dict | str) -> None:
        self._store[name] = my_secret

    def load_secret(self, name: str) -> Dict | str | None:
        return self._store.get(name)

    @classmethod
    def instantiate_secret_manager(
        cls, info: Dict[str, Any]
    ) -> "SerializableSecretManager":
        return cls(info.get("secrets", {}))

    def get_access_secrets(self) -> Dict[str, Any]:
        return {"secrets": dict(self._store)}

    @property
    def supports_keyfile_export(self) -> bool:
        return True
