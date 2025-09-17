"""Provides GCP Secret Manager functions.

To access the secret manager, a service account with the following roles is necessary:
    1. secret manager secret accessor (view and read secret contents)
    2. secret manager viewer (list secrets)
    3. secret manager admin (create and update secrets and versions)

Author: nicococo|mlox
"""

import json
import logging

from typing import Dict, Tuple, List, Any
from dataclasses import dataclass, field

from google.cloud import secretmanager
from google.api_core import exceptions as g_exc
from google.oauth2.service_account import Credentials

from mlox.secret_manager import AbstractSecretManager

logger = logging.getLogger(__name__)


def dict_to_service_account_credentials(keyfile_dict: Dict) -> Credentials:
    """Translates a keyfile dictionary into a service account credential either using oauth2
        or google oauth client.

    Args:
        keyfile_dict (Dict): keyfile dict

    Returns:
        service_account.Credentials: GCP service account credentials
    """
    credentials = None
    try:
        credentials = Credentials.from_service_account_info(keyfile_dict)
    except Exception as e:
        logger.error(f"Failed to load credentials from keyfile: {e}")
        raise ValueError("Failed to load credentials from provided keyfile.")
    return credentials


@dataclass
class GCPSecretManager(AbstractSecretManager):
    keyfile_dict: Dict | None = field(default=None, init=True)
    _secret_cache: Dict[str, Tuple[int, str]] = field(default_factory=dict, init=False)
    _project_id: str = field(default="", init=False)

    def __post_init__(self):
        """Post-initialization to set up the project ID."""
        if not self.keyfile_dict:
            raise ValueError(
                "Keyfile dictionary must be provided for GCP Secret Manager."
            )
        self._project_id = self.keyfile_dict.get("project_id", "")
        if not self._project_id:
            raise ValueError(
                "Project ID is missing in the provided keyfile dictionary."
            )
        logger.info(f"GCP Secret Manager initialized for project: {self._project_id}")

    def _get_credentials(self) -> Credentials | None:
        """Helper to load GCP credentials from various sources."""
        credentials = None
        if self.keyfile_dict:
            credentials = dict_to_service_account_credentials(self.keyfile_dict)
        else:
            logger.error("Keyfile JSON is not provided.")
        return credentials

    def is_working(self) -> bool:
        return self._get_credentials() is not None

    def list_secrets(self, keys_only: bool = False) -> Dict[str, Any]:
        """List all secrets stored in the secret manager."""
        return {
            name: self.load_secret(name) if not keys_only else None
            for name in self._list_secrets()
        }

    def _list_secrets(self) -> List[str]:
        """Lists all secret names in the configured GCP project.

        Returns:
            List[str]: A list of secret names, or an empty list on error.
        """
        secret_names: List[str] = []
        try:
            credentials = self._get_credentials()
            client = secretmanager.SecretManagerServiceClient(credentials=credentials)

            parent = f"projects/{self._project_id}"

            # The list_secrets method returns an iterator. We loop through it
            # to get all the secrets.
            for secret in client.list_secrets(request={"parent": parent}):
                # The 'secret.name' attribute is the full resource name, e.g.,
                # 'projects/{project_id}/secrets/{secret_id}'. We parse out the ID.
                secret_id = secret.name.split("/")[-1]
                secret_names.append(secret_id)

        except Exception as e:
            logger.error(f"Failed to list secrets: {e}")

        return secret_names

    def save_secret(self, name: str, my_secret: Dict | str) -> None:
        """Saves a secret to GCP Secret Manager.

        Creates the secret container if it doesn't exist, then adds the
        payload as a new version.

        Args:
            name: The name/ID of the secret.
            secret: The dictionary or str content to save.
        """
        try:
            credentials = self._get_credentials()
            client = secretmanager.SecretManagerServiceClient(credentials=credentials)
            parent = f"projects/{self._project_id}"
            secret_path = f"{parent}/secrets/{name}"

            # Try to create the secret container. If it already exists, that's fine.
            try:
                client.create_secret(
                    request={
                        "parent": parent,
                        "secret_id": name,
                        "secret": {"replication": {"automatic": {}}},
                    }
                )
                logger.info(f"Created new secret container: '{name}'")
            except g_exc.AlreadyExists:
                logger.info(f"Secret '{name}' already exists. Adding a new version.")

            # Convert dict to bytes for the payload
            payload_bytes = json.dumps(my_secret, indent=2).encode("UTF-8")

            # Add the secret payload as a new version
            response = client.add_secret_version(
                request={"parent": secret_path, "payload": {"data": payload_bytes}}
            )
            logger.info(f"Added new version to secret '{name}': {response.name}")

        except Exception as e:
            logger.error(f"Failed to save secret '{name}': {e}")

    def load_secret(self, name: str) -> Dict | str | None:
        """Load a secret from the secret manager."""
        ret = self.read_secret_as_raw_token(name)  # Update usage counter
        if ret is None:
            return None
        try:
            # Try to parse the secret as JSON
            return json.loads(ret)
        except json.JSONDecodeError:
            # If it fails, return the raw string
            return ret

    def read_secret_as_raw_token(
        self, secret_name: str, version: str = "latest"
    ) -> str | None:
        """Load a raw secret token from gcloud secret manager.

        Args:
            secret_name (str): Name of the google secret manager secret. Only latest version is used.
            version (str): (Optional) The secret version. If not provided then the latest version is used.

        Returns:
            str: - Content of the latest secret as str.
                - None, if some exception occured (e.g. no internet connection)
        """
        if secret_name in self._secret_cache:
            self._secret_cache[secret_name] = (
                self._secret_cache[secret_name][0] + 1,
                self._secret_cache[secret_name][1],
            )  # increase usage counter
            return self._secret_cache[secret_name][1]

        payload = None
        try:
            credentials = self._get_credentials()
            client = secretmanager.SecretManagerServiceClient(credentials=credentials)

            SECRET_PATH_ID = (
                f"projects/{self._project_id}/secrets/{secret_name}/versions/{version}"
            )
            response = client.access_secret_version(request={"name": SECRET_PATH_ID})
            payload = response.payload.data.decode("UTF-8")
            self._secret_cache[secret_name] = (1, payload)
        except Exception as e:
            logger.error(f"Failed to read secret '{secret_name}': {e}")
        return payload

    def get_secret_usage_statistics(self) -> Dict:
        """Get a dictionary of used secrets and number of invokes.

        Returns:
            Dict: Dict of secret name and number of invokes
        """
        res = dict()
        for k, v in self._secret_cache.items():
            res[k] = v[0]
        return res

    @classmethod
    def instantiate_secret_manager(
        cls, info: Dict[str, Any]
    ) -> "GCPSecretManager | None":
        try:
            keyfile_dict = info.get("keyfile_dict", None)
            if not keyfile_dict:
                raise ValueError("Keyfile dictionary not found in info.")
            return GCPSecretManager(keyfile_dict=keyfile_dict)
        except Exception as e:
            logger.error(f"Error initializing GCP Secret Manager: {e}")
        return None

    def get_access_secrets(self) -> Dict[str, Any] | None:
        return {"keyfile_dict": self.keyfile_dict}


def read_keyfile(keyfile_path: str) -> Dict:
    """Read the GCP keyfile from a JSON file."""
    try:
        with open(keyfile_path, "r") as f:
            keyfile_dict = json.load(f)
        return keyfile_dict
    except Exception as e:
        logger.error(f"Failed to read keyfile '{keyfile_path}': {e}")
        raise ValueError("Could not read the GCP keyfile.")


def load_secret_from_gcp(keyfile: str, secret_name: str) -> dict | None:
    """Load a secret from GCP Secret Manager. This method loads a keyfile, creates a
    GCP Secret Manager instance and then extracts the secret with name `secret_name`. This
    is a shortcut method and only suitable when loading a single secret (ie for a sepcific service)
    otherwise creating a GCPSecretManager instance is recommended.

    Args:
        keyfile (str): The path and name of the service account keyfile (e.g. './keyfile.json')
        secret_name (str): The name of the secret to load.

    Returns:
        dict | None: Content of the service account keyfile as a dictionary.
    """
    keyfile_dict = read_keyfile(keyfile)
    sm = GCPSecretManager(keyfile_dict)
    if not sm.is_working():
        logger.error("Error: GCP Secret Manager is not working. Check your keyfile.")
        return None
    value = sm.load_secret(secret_name)
    if not value:
        logger.error(
            f"Error: Could not load secret '{secret_name}' from GCP Secret Manager."
        )
        return None
    if not isinstance(value, dict):
        logger.error(f"Error: Secret '{secret_name}' is not a dictionary.")
        return None
    return value


if __name__ == "__main__":
    keyfile_dict = read_keyfile("./keyfile.json")

    # with open("./keyfile.json", "r") as f:
    #     keyfile_dict = json.load(f)

    sm = GCPSecretManager(keyfile_dict=keyfile_dict)
    logger.info(f"Read secret #1: {sm.load_secret('MLOX_TEST_SECRET')}")
    logger.info(f"Read secret #2: {sm.load_secret('MLOX_TEST_SECRET')}")
    logger.info(f"Read secret #3: {sm.load_secret('MLOX_TEST_SECRET')}")

    logger.info("\n--- Saving a new or existing secret ---")
    sm.save_secret("MLOX_TEST_SECRET", {"key": "value", "timestamp": "now"})

    logger.info("\n--- Listing all secrets ---")
    logger.info(sm.list_secrets(keys_only=True))

    logger.info(f"Secret stats (#calls): {sm.get_secret_usage_statistics()}")
