import logging

from dataclasses import dataclass
from typing import Dict, Any

from mlox.servers.ubuntu.native import UbuntuNativeServer
from mlox.server import RemoteUser

logger = logging.getLogger(__name__)


@dataclass
class UbuntuSimpleServer(UbuntuNativeServer):
    """A minimal Ubuntu server that assumes access is already configured.

    No package installation, user creation or system updates are performed.
    The server can optionally connect using an existing SSH private key.
    """

    root_private_key: str | None = None
    root_passphrase: str | None = None

    def __post_init__(self):
        super().__post_init__()
        if self.root_private_key:
            remote = RemoteUser(ssh_passphrase=self.root_passphrase or "")
            remote.ssh_key = self.root_private_key
            self.remote_user = remote

    def setup(self) -> None:
        if self.state != "un-initialized":
            logging.error("Can not initialize an already initialized server.")
            return
        self.state = "starting"
        self.setup_backend()

    # The following methods are intentionally no-ops to keep the server minimal
    def update(self) -> None:
        logger.info("Skipping update for UbuntuSimpleServer.")

    def install_packages(self) -> None:
        logger.info("Skipping package installation for UbuntuSimpleServer.")

    def add_mlox_user(self) -> None:
        logger.info("Skipping mlox user creation for UbuntuSimpleServer.")

    def setup_users(self) -> None:
        logger.info("Skipping user setup for UbuntuSimpleServer.")

    def disable_password_authentication(self) -> None:
        logger.info("Skipping password authentication configuration for UbuntuSimpleServer.")

    def enable_password_authentication(self) -> None:
        logger.info("Skipping password authentication configuration for UbuntuSimpleServer.")

    def enable_debug_access(self) -> None:
        self.is_debug_access_enabled = True

    def disable_debug_access(self) -> None:
        self.is_debug_access_enabled = False

    def get_backend_status(self) -> Dict[str, Any]:
        return super().get_backend_status()
