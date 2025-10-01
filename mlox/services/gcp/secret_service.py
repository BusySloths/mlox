import logging

from dataclasses import dataclass
from typing import Dict, cast

from mlox.secret_manager import AbstractSecretManager, AbstractSecretManagerService
from mlox.service import AbstractService
from mlox.infra import Infrastructure
from mlox.services.gcp.secret_manager import GCPSecretManager


logger = logging.getLogger(__name__)


@dataclass
class GCPSecretService(AbstractService, AbstractSecretManagerService):
    secret_name: str
    secret_manager_uuid: str

    def __post_init__(self):
        self.state = "running"

    def get_secret_manager(self, infra: Infrastructure) -> AbstractSecretManager:
        keyfile_dict = dict()
        service = infra.get_service_by_uuid(self.secret_manager_uuid)
        if not service:
            raise ValueError(
                f"Secret manager service with UUID {self.secret_manager_uuid} not found."
            )
        if hasattr(service, "get_secret_manager"):
            sms = cast(AbstractSecretManagerService, service)
            sm = sms.get_secret_manager(infra)
            secret = sm.load_secret(self.secret_name)
            if isinstance(secret, dict):
                keyfile_dict = secret
        return GCPSecretManager(keyfile_dict=keyfile_dict)

    def setup(self, conn) -> None:
        self.service_urls = dict()
        self.service_ports = dict()
        self.state = "running"

    def teardown(self, conn):
        self.state = "un-initialized"

    def spin_up(self, conn):
        return None

    def spin_down(self, conn):
        return None

    def check(self, conn) -> Dict:
        return dict()

    def get_secrets(self) -> Dict[str, Dict]:
        return {}
    