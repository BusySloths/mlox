import os
import logging

from datetime import datetime, timezone

from typing import List, Optional, Dict, Any
from dataclasses import dataclass, field

from mlox.migrations.base import MloxMigrations
from mlox.infra import Infrastructure
from mlox.secret_manager import AbstractSecretManager, InMemorySecretManager
from mlox.utils import (
    dataclass_to_dict,
    save_to_json,
    load_from_json,
    dict_to_dataclass,
)
from mlox.scheduler import ProcessScheduler

logger = logging.getLogger(__name__)


class GlobalProcessScheduler:
    """
    Global process scheduler instance for managing background jobs.
    This is a singleton to ensure only one instance is used across the application.
    """

    _instance: Optional["GlobalProcessScheduler"] = None
    scheduler: ProcessScheduler

    def init_scheduler(self):
        self.scheduler = ProcessScheduler(
            max_processes=2,
            watchdog_wakeup_sec=1.0,
            watchdog_timeout_sec=1500.0,
            disable_garbage_collection=False,
        )

    def __new__(cls) -> "GlobalProcessScheduler":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance.init_scheduler()
        return cls._instance


@dataclass
class MloxProject:
    name: str
    descr: str = field(default="", init=False)
    version: str = field(default="0.1.0", init=False)
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    last_opened_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    secret_manager_class: str | None = None
    secret_manager_info: Dict[str, Any] = field(default_factory=dict)

    def touch(self) -> None:
        self.last_opened_at = datetime.now(timezone.utc).isoformat()


class MloxSession:
    password: str
    project: MloxProject
    infra: Infrastructure
    secrets: AbstractSecretManager | None = None
    migrations: List[MloxMigrations] | None = None

    def __init__(
        self,
        project_name: str,
        password: str,
        migrations: List[MloxMigrations] | None = None,
    ):
        # self.scheduler = GlobalProcessScheduler().scheduler
        self.secrets = None
        self.password = password
        self.migrations = migrations
        self.load_project(project_name)
        self.load_secret_manager()
        self.load_infrastructure()
        if not self.secrets:
            logger.info(
                "No secret manager could be loaded. Initialising in-memory secret manager."
            )
            self.set_secret_manager(InMemorySecretManager())

    def save_project(self) -> None:
        self.project.touch()
        if self.secrets:
            info = self.secrets.get_access_secrets()
            if info:
                self.project.secret_manager_info = info
            else:
                logger.warning(
                    "Secret manager %s did not return any access info.",
                    self.project.secret_manager_class,
                )

        prj_dict = dataclass_to_dict(self.project)
        if prj_dict:
            save_to_json(
                prj_dict, f"./{self.project.name}.project", self.password, True
            )

    @classmethod
    def check_project_exists_and_loads(cls, project_name: str, password: str) -> bool:
        load_path = f"/{project_name}.project"
        try:
            _ = load_from_json(load_path, password, encrypted=True)
            return True
        except Exception:
            return False

    def load_project(self, project_name: str) -> None:
        load_path = f"/{project_name}.project"
        try:
            data = load_from_json(load_path, self.password, encrypted=True)
            project = dict_to_dataclass(data, [MloxProject])
            if not project or not isinstance(project, MloxProject):
                raise ValueError("Loaded project data is not valid.")
        except FileNotFoundError:
            logger.info("Project file not found for %s. Initialising a blank project.")
            project = MloxProject(name=project_name)
        project.touch()
        self.project = project
        self.save_project()

    def set_secret_manager(self, sm: AbstractSecretManager) -> None:
        self.secrets = sm
        if sm:
            self.project.secret_manager_class = (
                sm.__class__.__module__ + "." + sm.__class__.__name__
            )
        else:
            self.project.secret_manager_class = None
            self.project.secret_manager_info = {}
        self.save_project()

    def load_secret_manager(self) -> None:
        info = self.project.secret_manager_info
        class_name = self.project.secret_manager_class
        if not class_name:
            return None
        try:
            module_path, class_name = class_name.rsplit(".", 1)
            module = __import__(module_path, fromlist=[class_name])
            class_ = getattr(module, class_name)
            self.secrets = class_.instantiate_secret_manager(info)
            if not self.secrets:
                logger.warning(
                    "Secret manager class %s could not be instantiated.",
                    self.project.secret_manager_class,
                )
        except (ImportError, AttributeError) as e:
            logger.error(
                f"Could not load secret manager class {self.project.secret_manager_class}: {e}"
            )
            self.secrets = None

    def save_infrastructure(self) -> None:
        if not self.secrets:
            logger.info(
                "No secret manager configured for project %s. Skipping infrastructure persistence.",
                self.project,
            )
            return
        infra_dict = self.infra.to_dict()
        self.secrets.save_secret("MLOX_CONFIG_INFRASTRUCTURE", infra_dict)
        self.save_project()

    def load_infrastructure(self) -> None:
        if not self.secrets:
            logger.info(
                "No secret manager configured for project %s. Initialising blank infrastructure.",
                self.project,
            )
            self.infra = Infrastructure()
            return None
        logger.info(
            "Loading infrastructure for project %s from secret manager.",
            self.project.name,
        )
        infra_dict = self.secrets.load_secret("MLOX_CONFIG_INFRASTRUCTURE")
        if not infra_dict:
            self.infra = Infrastructure()
            return None
        if not isinstance(infra_dict, dict):
            raise ValueError("Infrastructure data is not in the expected format.")
        if self.migrations:
            for migration in self.migrations:
                logger.info(f"Applying migration: {migration.name}")
                infra_dict = migration._migrate_childs(infra_dict)
        self.infra = Infrastructure.from_dict(infra_dict)


def load_mlox_session(migrations: List[MloxMigrations] | None = None) -> MloxSession:
    mlox_name = os.environ.get("MLOX_PROJECT_NAME", None)
    mlox_password = os.environ.get("MLOX_PROJECT_PASSWORD", None)
    # Make sure your environment variable is set!
    if not mlox_password or not mlox_name:
        print(
            "Error: MLOX_PROJECT_PASSWORD or MLOX_PROJECT_NAME environment variable is not set."
        )
        exit(1)
    return MloxSession(mlox_name, mlox_password, migrations=migrations)
