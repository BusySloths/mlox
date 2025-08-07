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
from mlox.remote import fs_delete_dir
from mlox.infra import Infrastructure, Bundle

from mlox.server import AbstractServer
from mlox.utils import load_from_json, dict_to_dataclass

# Configure logging (optional, but recommended)
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)


@dataclass
class TSMService(AbstractService, AbstractSecretManagerService):
    pw: str
    server_uuid: str | None = field(default=None, init=False)
    secrets_abs_path: str | None = field(default=None, init=False)

    def __post_init__(self):
        self.state = "running"

    def get_secret_manager(self, infra: Infrastructure) -> AbstractSecretManager:
        """Get the TinySecretManager instance for this service."""
        if self.server_uuid is None:
            self.server_uuid = infra.bundles[0].server.uuid

        server = infra.get_server_by_uuid(self.server_uuid)
        if server is None:
            raise ValueError(
                f"Server with UUID {self.server_uuid} not found in infrastructure."
            )
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

    def get_absolute_path(self) -> str:
        """Get the absolute path to the secrets directory."""
        if self.secrets_abs_path is not None:
            return self.secrets_abs_path
        return self.target_path

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


def load_secret_manager_from_keyfile(path: str, pw: str) -> AbstractSecretManager:
    """
    Get a TinySecretManager instance for the given path and password.
    This is a utility function to create a secret manager without needing an infrastructure context.
    """

    keyfile_dict = load_from_json(path, pw)
    if not keyfile_dict:
        raise ValueError(
            f"Could not load keyfile from {path} with the provided password."
        )

    if "secrets_path" not in keyfile_dict or "secrets_pw" not in keyfile_dict:
        raise ValueError(f"Keyfile {path} does not contain secrets information.")
    path = keyfile_dict["secrets_path"]
    pw = keyfile_dict["secrets_pw"]
    print(path)

    if "server" not in keyfile_dict:
        raise ValueError(f"Keyfile {path} does not contain server information.")
    # server = dict_to_dataclass(keyfile_dict["server"], hooks=[AbstractServer])
    server_dict = keyfile_dict["server"]
    return TinySecretManager("", "", pw, server_dict=server_dict, secrets_abs_path=path)


if __name__ == "__main__":
    import os

    sm = load_secret_manager_from_keyfile(
        "/tsm.key", os.getenv("MLOX_TSM_KEYFILE_PW", "no_password")
    )
    if sm.is_working():
        print("Secret Manager is working.")
    else:
        print("Secret Manager is not working.")
    print(sm.list_secrets(keys_only=True))
