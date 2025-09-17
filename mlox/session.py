import logging
from datetime import datetime

from typing import Optional, Dict, Any
from dataclasses import dataclass, field

from mlox.config import load_config, get_stacks_path
from mlox.infra import Infrastructure
from mlox.secret_manager import TinySecretManager, AbstractSecretManager
from mlox.utils import dataclass_to_dict, save_to_json, load_from_json
from mlox.scheduler import ProcessScheduler


# Configure logging (optional, but recommended)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(module)s.%(funcName)s:%(lineno)d | %(message)s",
)
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


PROJECT_SECRET_MANAGER_KEY = "secret_manager"


@dataclass
class MloxProject:
    name: str
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    last_opened_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    secret_manager_service_uuid: Optional[str] = None
    additional_info: Dict[str, Any] = field(default_factory=dict)

    def touch(self) -> None:
        self.last_opened_at = datetime.utcnow().isoformat()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "created_at": self.created_at,
            "last_opened_at": self.last_opened_at,
            "secret_manager_service_uuid": self.secret_manager_service_uuid,
            "additional_info": self.additional_info,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MloxProject":
        return cls(
            name=data.get("name", ""),
            created_at=data.get("created_at", datetime.utcnow().isoformat()),
            last_opened_at=data.get("last_opened_at", datetime.utcnow().isoformat()),
            secret_manager_service_uuid=data.get("secret_manager_service_uuid"),
            additional_info=data.get("additional_info") or {},
        )

    def get_secret_manager_info(self) -> Optional[Dict[str, Any]]:
        info = self.additional_info.get(PROJECT_SECRET_MANAGER_KEY)
        if isinstance(info, dict):
            return info
        return None

    def set_secret_manager_info(
        self,
        service_uuid: str,
        keyfile: Dict[str, Any],
        secrets_path: str,
        password: Optional[str] = None,
        relative_path: Optional[str] = None,
    ) -> None:
        payload: Dict[str, Any] = {
            "keyfile": keyfile,
            "secrets_path": secrets_path,
        }
        if password:
            payload["password"] = password
        if relative_path:
            payload["relative_path"] = relative_path
        self.secret_manager_service_uuid = service_uuid
        self.additional_info[PROJECT_SECRET_MANAGER_KEY] = payload


@dataclass
class MloxSession:
    username: str
    password: str

    project: MloxProject = field(init=False)
    infra: Infrastructure = field(init=False)
    secrets: Optional[AbstractSecretManager] = field(default=None, init=False)
    # scheduler: ProcessScheduler = field(init=False)

    temp_kv: dict = field(default_factory=dict, init=False)

    def __post_init__(self):
        # self.scheduler = GlobalProcessScheduler().scheduler
        self.project = self._load_or_create_project()
        self.infra = Infrastructure()
        self.secrets = self._init_secret_manager()
        if self.secrets and self.secrets.is_working():
            self.load_infrastructure()
        else:
            self.infra = Infrastructure()

    def _get_project_save_path(self) -> str:
        return f"./{self.username}.project"

    def _get_project_load_path(self) -> str:
        return f"/{self.username}.project"

    def _persist_project(self, project: Optional[MloxProject] = None) -> None:
        target = project if project is not None else getattr(self, "project", None)
        if not target:
            return
        save_to_json(target.to_dict(), self._get_project_save_path(), self.password, True)

    def _load_or_create_project(self) -> MloxProject:
        load_path = self._get_project_load_path()
        try:
            data = load_from_json(load_path, self.password)
            project = MloxProject.from_dict(data)
        except FileNotFoundError:
            logger.info(
                "Project file not found for %s. Initialising a blank project.",
                self.username,
            )
            project = MloxProject(name=self.username)
            self._persist_project(project)
        except Exception as exc:
            logger.error(
                "Failed to load project information for %s: %s",
                self.username,
                exc,
            )
            raise
        project.touch()
        self._persist_project(project)
        return project

    def _init_secret_manager(self) -> Optional[AbstractSecretManager]:
        info = self.project.get_secret_manager_info()
        if not info:
            return None
        keyfile = info.get("keyfile")
        if not keyfile:
            logger.warning(
                "Project %s is missing keyfile data for the secret manager.",
                self.username,
            )
            return None
        secret_password = info.get("password", self.password)
        secrets_path = info.get("secrets_path")
        relative_path = info.get("relative_path")
        try:
            if secrets_path:
                return TinySecretManager(
                    "",
                    "",
                    secret_password,
                    server_dict=keyfile,
                    secrets_abs_path=secrets_path,
                )
            relative_arg = relative_path if relative_path else ".secrets"
            return TinySecretManager(
                "",
                relative_arg,
                secret_password,
                server_dict=keyfile,
            )
        except Exception as exc:
            logger.error(
                "Failed to initialize secret manager for project %s: %s",
                self.username,
                exc,
            )
            return None

    @classmethod
    def new_infrastructure(
        cls, infra, config, params, username, password
    ) -> Optional["MloxSession"]:
        # STEP 1: Instantiate the server template
        server_bundle = infra.add_server(config, params)
        if not server_bundle:
            logger.error("Failed to instantiate server template.")
            return None

        # STEP 2: Initialize the server
        try:
            server_bundle.server.setup()
        except Exception as e:
            logger.error(f"Server setup failed: {e}")
            if not (server_bundle.server.mlox_user and server_bundle.server.remote_user):
                logger.error(
                    "Could not setup user. Check server credentials and try again."
                )
                return None

        project = MloxProject(name=username)

        # STEP 3: Configure the secret manager service
        secret_manager_config = load_config(get_stacks_path(), "/tsm", "mlox.tsm.yaml")
        if not secret_manager_config:
            logger.error("Failed to load secret manager configuration.")
            return None

        secret_bundle = infra.add_service(
            server_bundle.server.ip, secret_manager_config, {}
        )
        if not secret_bundle or not secret_bundle.services:
            logger.error("Failed to instantiate secret manager service.")
            return None

        secret_service = secret_bundle.services[0]
        secret_service.pw = password
        secret_bundle.tags.append("mlox.secrets")
        secret_bundle.tags.append("mlox.primary")

        secrets_path = (
            secret_service.get_absolute_path()
            if hasattr(secret_service, "get_absolute_path")
            else secret_service.target_path
        )
        relative_path = None
        if (
            server_bundle.server.mlox_user
            and isinstance(secrets_path, str)
            and secrets_path.startswith(server_bundle.server.mlox_user.home)
        ):
            relative_path = secrets_path.removeprefix(
                server_bundle.server.mlox_user.home
            ).lstrip("/")

        project.set_secret_manager_info(
            secret_service.uuid,
            dataclass_to_dict(server_bundle.server),
            secrets_path,
            password=secret_service.pw,
            relative_path=relative_path,
        )

        # Persist the project metadata and keyfile information
        save_to_json(project.to_dict(), f"./{username}.project", password, True)

        ms = MloxSession(username, password)
        if project.get_secret_manager_info():
            if not ms.secrets or not ms.secrets.is_working():
                logger.error("Secret manager setup failed.")
                return None

        # STEP 4: Persist the infrastructure to the secret manager (if available)
        ms.infra = infra
        if ms.secrets and ms.secrets.is_working():
            ms.save_infrastructure()
        else:
            logger.info(
                "No secret manager configured for project %s; infrastructure not persisted.",
                username,
            )

        return ms

    def save_infrastructure(self) -> None:
        if not self.secrets:
            logger.info(
                "No secret manager configured for project %s. Skipping infrastructure persistence.",
                self.username,
            )
            return
        infra_dict = self.infra.to_dict()
        self.secrets.save_secret("MLOX_CONFIG_INFRASTRUCTURE", infra_dict)

    def load_infrastructure(self) -> None:
        if not self.secrets:
            self.infra = Infrastructure()
            return None
        infra_dict = self.secrets.load_secret("MLOX_CONFIG_INFRASTRUCTURE")
        if not infra_dict:
            self.infra = Infrastructure()
            return None
        if not isinstance(infra_dict, dict):
            raise ValueError("Infrastructure data is not in the expected format.")
        self.infra = Infrastructure.from_dict(infra_dict)
