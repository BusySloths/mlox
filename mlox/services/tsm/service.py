import logging

from dataclasses import dataclass, field
from typing import Dict

from mlox.utils import dataclass_to_dict
from mlox.secret_manager import (
    TinySecretManager,
    AbstractSecretManager,
    AbstractSecretManagerService,
)
from mlox.service import AbstractService
from mlox.server import AbstractServer
from mlox.remote import fs_delete_dir

# Configure logging (optional, but recommended)
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)


@dataclass
class TSMService(AbstractService, AbstractSecretManagerService):
    pw: str
    secrets_abs_path: str | None = field(default=None, init=False)

    def __post_init__(self):
        self.state = "running"

    def get_secret_manager(self, server: AbstractServer) -> AbstractSecretManager:
        """Get the TinySecretManager instance for this service."""
        server_dict = dataclass_to_dict(server)

        if self.secrets_abs_path is not None:
            return TinySecretManager(
                "",
                "",
                self.pw,
                server_dict=server_dict,
                secrets_abs_path=self.secrets_abs_path,
            )

        if server.mlox_user is None:
            raise ValueError("Server user is not set.")
        relative_path = self.target_path.removeprefix(server.mlox_user.home)
        return TinySecretManager("", relative_path, self.pw, server_dict=server_dict)

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
