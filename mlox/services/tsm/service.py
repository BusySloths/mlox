import logging

from dataclasses import dataclass
from typing import Dict

from mlox.utils import dataclass_to_dict, save_to_json
from mlox.infra import Bundle
from mlox.secret_manager import TinySecretManager
from mlox.service import AbstractService, tls_setup
from mlox.remote import (
    fs_copy,
    fs_delete_dir,
    fs_create_dir,
    fs_create_empty_file,
    fs_append_line,
    sys_user_id,
    docker_down,
)

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
        self.service_url = "None"
        self.service_ports = dict()

    def teardown(self, conn):
        fs_delete_dir(conn, self.target_path)

    def spin_up(self, conn):
        return None

    def check(self, conn) -> Dict:
        return dict()
