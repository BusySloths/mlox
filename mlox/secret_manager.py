import os
import json
import logging

from cryptography.fernet import Fernet

from abc import ABC, abstractmethod
from typing import Any, Dict, Mapping, cast
from dataclasses import dataclass

from mlox.server import AbstractServer
import importlib
from mlox.utils import (
    _get_encryption_key,
    dict_to_dataclass,
    decrypt_dict,
    encrypt_dict,
    load_from_json,
    dataclass_to_dict,
)


SECRET_MANAGER_KEYFILE_ENV = "MLOX_SECRET_MANAGER_KEYFILE"
SECRET_MANAGER_KEYFILE_PW_ENV = "MLOX_SECRET_MANAGER_KEYFILE_PW"


@dataclass
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

    @classmethod
    @abstractmethod
    def instantiate_secret_manager(
        cls, info: Dict[str, Any]
    ) -> "AbstractSecretManager | None":
        """Load the infrastructure configuration from the secret manager."""
        pass

    @abstractmethod
    def get_access_secrets(self) -> Dict[str, Any] | None:
        """Get MLOX access information from the secret manager."""
        pass

    @property
    def supports_keyfile_export(self) -> bool:
        return False


@dataclass
class TinySecretManager(AbstractSecretManager):
    """A simple secret manager that encrypts and decrypts secrets saved on a remote machine."""

    path: str
    master_token: str
    server: AbstractServer
    cache: Dict[str, Any]
    _connection_works: bool = False

    def __init__(
        self,
        server_config_file: str,
        secrets_relative_path: str,
        master_token: str,
        server_dict: Dict[str, Any] | None = None,
        secrets_abs_path: str | None = None,
    ):
        self.cache = {}
        self.master_token = master_token

        if not server_dict:
            server_dict = load_from_json(server_config_file, master_token)

        if not server_dict:
            raise ValueError(
                "Server configuration is missing or invalid. Cannot initialize TinySecretManager."
            )
        server = dict_to_dataclass(server_dict, [AbstractServer])
        if not server:
            raise ValueError("Server is not set. Cannot initialize TinySecretManager.")
        self.server = server
        if not server.mlox_user:
            raise ValueError(
                "Server user is not set. Cannot initialize TinySecretManager."
            )
        if secrets_abs_path:
            self.path = secrets_abs_path
        else:
            self.path = f"{server.mlox_user.home}/{secrets_relative_path}"
        with server.get_server_connection() as conn:
            executor = server.exec
            executor.fs_create_dir(conn, self.path)
            if conn.is_connected:
                self._connection_works = True
        list_secrets = self.list_secrets(keys_only=False, use_cache=False)
        self.cache.update(list_secrets)

    def is_working(self) -> bool:
        return self._connection_works

    def list_secrets(
        self, keys_only: bool = False, use_cache: bool = True
    ) -> Dict[str, Any]:
        if use_cache:
            if keys_only:
                return {k: None for k in self.cache.keys()}
            return self.cache
        secrets: Dict[str, Any] = {}
        executor = self.server.exec
        with self.server.get_server_connection() as conn:
            files = executor.fs_list_files(conn, self.path)
            for file in files:
                if file.endswith(".json"):
                    name = file[:-5]
                    if keys_only:
                        secrets[name] = None
                    else:
                        secret_value = None
                        try:
                            file_path = f"{self.path}/{file}"
                            encrypted_data = executor.fs_read_file(
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
        executor = self.server.exec
        with self.server.get_server_connection() as conn:
            executor.fs_touch(conn, filepath)

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

        executor = self.server.exec
        with self.server.get_server_connection() as conn:
            executor.fs_write_file(conn, filepath, encrypted_data)

        self.cache[name] = my_secret

    def load_secret(self, name: str) -> Dict | str | None:
        if name in self.cache:
            return self.cache[name]
        name += ".json"
        filepath = os.path.join(self.path, name)

        encrypted_data = None
        executor = self.server.exec
        with self.server.get_server_connection() as conn:
            try:
                encrypted_data = executor.fs_read_file(
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

    @classmethod
    def instantiate_secret_manager(
        cls, info: Dict[str, Any]
    ) -> "AbstractSecretManager | None":
        try:
            server_dict = info.get("keyfile", None)
            password = info.get("secrets_master_token", None)
            abs_path = info.get("secrets_abs_path", None)
            return TinySecretManager(
                "", "", password, server_dict=server_dict, secrets_abs_path=abs_path
            )
        except Exception as e:
            logging.error(f"Error initializing secret manager: {e}")
        return None

    def get_access_secrets(self) -> Dict[str, Any] | None:
        server_dict = dataclass_to_dict(self.server)
        return {
            "keyfile": server_dict,
            "secrets_abs_path": self.path,
            "secrets_master_token": self.master_token,
        }

    @property
    def supports_keyfile_export(self) -> bool:
        return True


def get_encrypted_access_keyfile(
    secret_manager: AbstractSecretManager, keyfile_pw: str
) -> str:
    if not secret_manager.supports_keyfile_export:
        raise ValueError(
            f"{secret_manager.__class__.__name__} does not support keyfile export."
        )
    access_secret_dict = secret_manager.get_access_secrets()
    access_config = {
        "access_secret": access_secret_dict,
        "secret_manager_class": f"{secret_manager.__class__.__module__}.{secret_manager.__class__.__qualname__}",
    }
    encrypted_keyfile_dict = encrypt_dict(access_config, keyfile_pw)
    return encrypted_keyfile_dict


def _instantiate_secret_manager_from_access_secret(
    secret_manager_class: str, access_secret: Dict[str, Any]
) -> AbstractSecretManager | None:
    module_name, class_name = secret_manager_class.rsplit(".", 1)
    module = importlib.import_module(module_name)
    sm_class = getattr(module, class_name)
    sm_class = cast(type[AbstractSecretManager], sm_class)
    return sm_class.instantiate_secret_manager(access_secret)


def _instantiate_secret_manager_from_keyfile_data(
    keyfile_data: Dict[str, Any]
) -> AbstractSecretManager | None:
    secret_manager_class = keyfile_data["secret_manager_class"]
    access_secret = keyfile_data["access_secret"]
    if not secret_manager_class or not isinstance(access_secret, dict):
        logging.error("Invalid keyfile format.")
        return None
    try:
        return _instantiate_secret_manager_from_access_secret(
            secret_manager_class, access_secret
        )
    except Exception as e:
        logging.error(
            f"Error loading secret manager class '{secret_manager_class}': {e}"
        )
    return None


def load_secret_manager_from_keyfile(
    encrypted_access_keyfile: str, keyfile_pw: str
) -> AbstractSecretManager | None:
    try:
        # Part I: Load and decrypt the keyfile
        keyfile_data = load_from_json(encrypted_access_keyfile, keyfile_pw)
        logging.warning(f"Loaded keyfile data: {keyfile_data}")
    except Exception as e:
        logging.error(
            f"Error loading secret manager access secret '{encrypted_access_keyfile}': {e}"
        )
        return None
    return _instantiate_secret_manager_from_keyfile_data(keyfile_data)


def load_secret_manager_from_env(
    encrypted_access_keyfile_env: str = SECRET_MANAGER_KEYFILE_ENV,
    keyfile_pw_env: str = SECRET_MANAGER_KEYFILE_PW_ENV,
    environ: Mapping[str, str] | None = None,
) -> AbstractSecretManager | None:
    """Load a secret manager from environment variables.

    ``encrypted_access_keyfile_env`` must contain the same encrypted keyfile
    content consumed by ``load_secret_manager_from_keyfile``.
    """
    env = os.environ if environ is None else environ
    encrypted_access_keyfile = env.get(encrypted_access_keyfile_env)
    keyfile_pw = env.get(keyfile_pw_env)

    if not encrypted_access_keyfile or not keyfile_pw:
        logging.error(
            "Secret manager environment variables '%s' and '%s' must be set.",
            encrypted_access_keyfile_env,
            keyfile_pw_env,
        )
        return None

    try:
        keyfile_data = decrypt_dict(encrypted_access_keyfile, keyfile_pw)
        logging.warning(f"Loaded keyfile data from environment: {keyfile_data}")
    except Exception as e:
        logging.error(
            "Error loading secret manager access secret from environment '%s': %s",
            encrypted_access_keyfile_env,
            e,
        )
        return None

    return _instantiate_secret_manager_from_keyfile_data(keyfile_data)
