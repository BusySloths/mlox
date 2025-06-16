import os
import json
import logging

from cryptography.fernet import Fernet

from abc import ABC, abstractmethod
from typing import Any, Dict

from mlox.server import AbstractServer
from mlox.utils import _get_encryption_key, dict_to_dataclass, load_from_json
from mlox.remote import (
    fs_create_dir,
    fs_touch,
    fs_read_file,
    fs_write_file,
    fs_list_files,
)


class AbstractSecretManager(ABC):
    """A simple interface for secret managers."""

    @abstractmethod
    def is_working(self) -> bool:
        """Check if the secret manager is working."""
        pass

    @abstractmethod
    def list_secrets(self, keys_only: bool = False) -> Dict[str, Any]:
        """List all secrets stored in the secret manager."""
        pass

    @abstractmethod
    def save_secret(self, name: str, my_secret: Dict | str) -> None:
        """Save a secret to the secret manager."""
        pass

    @abstractmethod
    def load_secret(self, name: str) -> Dict | str | None:
        """Load a secret from the secret manager."""
        pass


class TinySecretManager:
    """A simple secret manager that encrypts and decrypts secrets saved on a remote machine."""

    path: str
    master_token: str
    server: AbstractServer
    cache: Dict[str, Any]
    _connection_works: bool = False

    def __init__(
        self, server_config_file: str, secrets_relative_path: str, master_token: str
    ):
        self.cache = {}
        self.master_token = master_token

        server_dict = load_from_json(server_config_file, master_token)
        server = dict_to_dataclass(server_dict, [AbstractServer])
        if not server:
            raise ValueError("Server is not set. Cannot initialize TinySecretManager.")
        self.server = server
        if not server.mlox_user:
            raise ValueError(
                "Server user is not set. Cannot initialize TinySecretManager."
            )
        self.path = f"{server.mlox_user.home}/{secrets_relative_path}"
        with server.get_server_connection() as conn:
            fs_create_dir(conn, self.path)
            if conn.is_connected:
                self._connection_works = True

    def is_working(self) -> bool:
        return self._connection_works

    def list_secrets(self, keys_only: bool = False) -> Dict[str, Any]:
        secrets: Dict[str, Any] = {}
        with self.server.get_server_connection() as conn:
            files = fs_list_files(conn, self.path)
            for file in files:
                if file.endswith(".json"):
                    name = file[:-5]
                    if keys_only:
                        secrets[name] = None
                    else:
                        secret_value = None
                        try:
                            file_path = f"{self.path}/{file}"
                            encrypted_data = fs_read_file(
                                conn, file_path, encoding="utf-8", format="json"
                            )
                            # Decrypt the data
                            key = _get_encryption_key(password=self.master_token)
                            fernet = Fernet(key)
                            json_string = fernet.decrypt(encrypted_data).decode("utf-8")
                            secret_value = json.loads(json_string)
                        except BaseException:
                            continue
                        secrets[name] = secret_value
        return secrets

    def save_secret(self, name: str, my_secret: Dict | str) -> None:
        name += ".json"
        filepath = os.path.join(self.path, name)
        with self.server.get_server_connection() as conn:
            fs_touch(conn, filepath)

        """Saves a secret to a file."""
        if isinstance(my_secret, str):
            # Check if it's already a valid JSON string
            try:
                my_secret = json.loads(my_secret)
            except json.JSONDecodeError:
                logging.info("Provided string secret is not valid JSON.")

        json_string = json.dumps(my_secret, indent=2)
        # Encrypt the JSON string
        key = _get_encryption_key(password=self.master_token)
        fernet = Fernet(key)
        encrypted_data = fernet.encrypt(json_string.encode("utf-8"))

        with self.server.get_server_connection() as conn:
            fs_write_file(conn, filepath, encrypted_data)

        self.cache[name] = my_secret

    def load_secret(self, name: str) -> Dict | str | None:
        if name in self.cache:
            return self.cache[name]
        name += ".json"
        filepath = os.path.join(self.path, name)

        encrypted_data = None
        with self.server.get_server_connection() as conn:
            try:
                encrypted_data = fs_read_file(
                    conn, filepath, encoding="utf-8", format="json"
                )
            except BaseException:
                logging.error(f"Error reading secret '{name}'.")
                return None

        # Decrypt the data
        key = _get_encryption_key(password=self.master_token)
        fernet = Fernet(key)
        try:
            json_string = fernet.decrypt(encrypted_data).decode("utf-8")
        except Exception as e:
            logging.error(f"Error decrypting secret '{name}': {e}")
            return None
        return json.loads(json_string)


if __name__ == "__main__":
    # Make sure your environment variable is set!
    password = os.environ.get("MLOX_CONFIG_PASSWORD", None)
    if not password:
        print("Error: MLOX_CONFIG_PASSWORD environment variable is not set.")
        exit(1)

    secret_manager = TinySecretManager("/mlox.key", ".secrets", password)
    # print(secret_manager.load_secret("TEST_SECRET"))
    # secret_manager.save_secret(
    #     "TEST_SECRET",
    #     {
    #         "superkey": "supervalue",
    #         "anotherkey": "anothervalue",
    #         "listkey": ["item1", "item2"],
    #     },
    # )
    infra = secret_manager.load_secret("MLOX_CONFIG_INFRASTRUCTURE")
    print(infra)
