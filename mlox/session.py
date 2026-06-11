"""Session orchestration backed by an encrypted, single-file MLOX project."""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List

from mlox.infra import Infrastructure
from mlox.migrations.base import MloxMigrations
from mlox.project.secret_manager import ProjectSecretManager
from mlox.project.store import ProjectDatabase, resolve_project_path
from mlox.secret_manager import AbstractSecretManager

logger = logging.getLogger(__name__)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class MloxProject:
    name: str
    id: str = ""
    descr: str = ""
    version: str = "1"
    created_at: str = field(default_factory=_now)
    last_opened_at: str = field(default_factory=_now)
    data_source_id: str = ""
    data_source_kind: str = "sqlcipher"
    data_source_location: str = "self"
    data_source_config: Dict[str, Any] = field(default_factory=dict)
    # Read-only legacy fields retained for dump recovery and old plugin compatibility.
    secret_manager_class: str | None = None
    secret_manager_info: Dict[str, Any] = field(default_factory=dict)

    def touch(self) -> None:
        self.last_opened_at = _now()


class MloxSession:
    """An authenticated handle to one project and its active data source."""

    def __init__(
        self,
        project_name: str,
        password: str,
        migrations: List[MloxMigrations] | None = None,
        *,
        create: bool = False,
    ) -> None:
        self.password = password
        self.migrations = migrations
        self.project_path = resolve_project_path(project_name)
        self.store = (
            ProjectDatabase.create(self.project_path, password, self.project_path.stem)
            if create
            else ProjectDatabase(self.project_path, password).open()
        )
        self.secrets: AbstractSecretManager = ProjectSecretManager(self.store)
        self.load_project(project_name)
        self.load_infrastructure()

    @classmethod
    def create(
        cls, project_name: str, password: str, migrations: List[MloxMigrations] | None = None
    ) -> "MloxSession":
        return cls(project_name, password, migrations=migrations, create=True)

    @classmethod
    def check_project_exists_and_loads(cls, project_name: str, password: str) -> bool:
        try:
            ProjectDatabase(project_name, password).open()
            return True
        except Exception:
            return False

    def load_project(self, project_name: str | None = None) -> None:
        self.project = MloxProject(**self.store.load_project())

    def save_project(self) -> None:
        self.project.touch()
        self.store.save_project(self.project)

    def load_secret_manager(self) -> None:
        """Compatibility no-op: project secrets always live in the project database."""
        self.secrets = ProjectSecretManager(self.store)

    def set_secret_manager(self, manager: AbstractSecretManager | None) -> None:
        """Import an external manager's secrets; never move persistence out of the project."""
        if manager is None or isinstance(manager, ProjectSecretManager):
            return
        for name, value in manager.list_secrets(keys_only=False).items():
            if name != "MLOX_CONFIG_INFRASTRUCTURE":
                self.secrets.save_secret(name, value)

    def load_infrastructure(self) -> None:
        self.infra = self.store.load_infrastructure()
        if self.migrations:
            payload = self.infra.to_dict()
            for migration in self.migrations:
                logger.info("Applying migration: %s", migration.name)
                payload = migration._migrate_childs(payload)
            self.infra = Infrastructure.from_dict(payload)
            self.save_infrastructure()

    def save_infrastructure(self) -> None:
        self.store.save_infrastructure(self.infra)
        self.save_project()


def load_mlox_session(migrations: List[MloxMigrations] | None = None) -> MloxSession:
    project = os.environ.get("MLOX_PROJECT_PATH") or os.environ.get("MLOX_PROJECT_NAME")
    password = os.environ.get("MLOX_PROJECT_PASSWORD")
    if not project or not password:
        raise RuntimeError(
            "MLOX_PROJECT_PATH and MLOX_PROJECT_PASSWORD environment variables are required."
        )
    return MloxSession(project, password, migrations=migrations)
