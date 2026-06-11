"""Authenticated runtime context for an encrypted MLOX project."""

from __future__ import annotations

import os

from mlox.project.aggregate import ProjectAggregate
from mlox.project.secret_manager import ProjectSecretManager
from mlox.project.store import ProjectDatabase
from mlox.secret_manager import AbstractSecretManager


class ProjectSession:
    """Own persistence, encryption credentials, and secrets for one project."""

    def __init__(
        self,
        store: ProjectDatabase,
        project: ProjectAggregate,
    ) -> None:
        self.store = store
        self.project = project
        self.secrets: AbstractSecretManager = ProjectSecretManager(store)

    @property
    def path(self):
        return self.store.path

    @property
    def password(self) -> str:
        return self.store.password

    @classmethod
    def open(
        cls,
        path: str,
        password: str,
    ) -> "ProjectSession":
        store = ProjectDatabase(path, password).open()
        return cls(store, store.load())

    @classmethod
    def create(
        cls,
        path: str,
        password: str,
    ) -> "ProjectSession":
        store = ProjectDatabase.create(path, password)
        return cls(store, store.load())

    @classmethod
    def can_open(cls, path: str, password: str) -> bool:
        try:
            ProjectDatabase(path, password).open()
            return True
        except Exception:
            return False

    def commit(self) -> None:
        self.project.touch()
        self.store.save(self.project)

    def reload(self) -> ProjectAggregate:
        self.project = self.store.load()
        return self.project

    def import_secrets(self, manager: AbstractSecretManager | None) -> None:
        if manager is None or isinstance(manager, ProjectSecretManager):
            return
        for name, value in manager.list_secrets(keys_only=False).items():
            if name != "MLOX_CONFIG_INFRASTRUCTURE":
                self.secrets.save_secret(name, value)


def load_project_session() -> ProjectSession:
    path = os.environ.get("MLOX_PROJECT_PATH") or os.environ.get("MLOX_PROJECT_NAME")
    password = os.environ.get("MLOX_PROJECT_PASSWORD")
    if not path or not password:
        raise RuntimeError(
            "MLOX_PROJECT_PATH and MLOX_PROJECT_PASSWORD environment variables are required."
        )
    return ProjectSession.open(path, password)
