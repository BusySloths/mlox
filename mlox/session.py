import logging

from typing import Optional, Any
from dataclasses import dataclass, field

from mlox.config import load_config
from mlox.infra import Infrastructure
from mlox.secret_manager import TinySecretManager, AbstractSecretManager
from mlox.utils import dataclass_to_dict, save_to_json
from mlox.scheduler import ProcessScheduler


# Configure logging (optional, but recommended)
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


@dataclass
class MloxSession:
    username: str
    password: str

    infra: Infrastructure = field(init=False)
    secrets: AbstractSecretManager = field(init=False)
    # scheduler: ProcessScheduler = field(init=False)

    temp_kv: dict = field(default_factory=dict, init=False)

    def __post_init__(self):
        # self.scheduler = ProcessScheduler(
        #     max_processes=1,
        #     watchdog_wakeup_sec=1,
        #     watchdog_timeout_sec=1500,
        #     disable_garbage_collection=False,
        # )
        # Add the process scheduler to take care of background jobs.
        self.secrets = TinySecretManager(
            f"/{self.username}.key", ".secrets", self.password
        )
        self.load_infrastructure()

    @classmethod
    def new_infrastructure(
        cls, infra, config, params, username, password
    ) -> Optional["MloxSession"]:
        # STEP 1: Instantiate the server template
        bundle = infra.add_server(config, params)
        if not bundle:
            logger.error("Failed to instantiate server template.")
            return None

        # STEP 2: Initialize the server
        try:
            bundle.server.setup()
        except Exception as e:
            logger.error(f"Server setup failed: {e}")
            if not (bundle.server.mlox_user and bundle.server.remote_user):
                logger.error(
                    f"Could not setup user. Check server credentials and try again."
                )
                return None

        # STEP 3: Generate the local key file
        try:
            server_dict = dataclass_to_dict(bundle.server)
            save_to_json(server_dict, f"./{username}.key", password, True)
        except Exception as e:
            logger.error(f"Generating key file failed: {e}")
            return None

        ms = MloxSession(username, password)
        if not ms.secrets.is_working():
            logger.error("Secret manager setup failed.")
            return None

        # STEP 4: Add the service to the infrastructure
        try:
            ms.infra = infra
            config = load_config("./stacks", "/tsm", "mlox.tsm.yaml")
            bundle = ms.infra.add_service(bundle.server.ip, config, {})
            bundle.services[0].pw = password
            bundle.tags.append("mlox.secrets")
            bundle.tags.append("mlox.primary")
            ms.save_infrastructure()
        except Exception as e:
            logger.error(f"Infrastructure setup failed: {e}")
            return None

        return ms

    def save_infrastructure(self) -> None:
        infra_dict = self.infra.to_dict()
        self.secrets.save_secret("MLOX_CONFIG_INFRASTRUCTURE", infra_dict)

    def load_infrastructure(self) -> None:
        infra_dict = self.secrets.load_secret("MLOX_CONFIG_INFRASTRUCTURE")
        if not infra_dict:
            self.infra = Infrastructure()
            return None
        if not isinstance(infra_dict, dict):
            raise ValueError("Infrastructure data is not in the expected format.")
        self.infra = Infrastructure.from_dict(infra_dict)
