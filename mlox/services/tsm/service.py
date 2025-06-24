import logging

from dataclasses import dataclass
from typing import Dict

from mlox.infra import Bundle
from mlox.utils import dataclass_to_dict
from mlox.secret_manager import TinySecretManager
from mlox.service import AbstractService
from mlox.remote import fs_delete_dir

# Configure logging (optional, but recommended)
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)


@dataclass
class TSMService(AbstractService):
    pw: str

    def get_secret_manager(self, bundle: Bundle) -> TinySecretManager:
        """Get the TinySecretManager instance for this service."""
        server_dict = dataclass_to_dict(bundle.server)
        return TinySecretManager("", self.target_path, self.pw, server_dict=server_dict)

    def setup(self, conn) -> None:
        self.service_urls = dict()
        self.service_ports = dict()
        self.state = "running"

    def teardown(self, conn):
        fs_delete_dir(conn, self.target_path)
        self.state = "un-initialized"

    def spin_up(self, conn):
        return None

    def check(self, conn) -> Dict:
        return dict()
