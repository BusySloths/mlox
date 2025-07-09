"""Provides GCP Secret Manager functions.

To access the secret manager, a service account with the following roles is necessary:
    1. secret manager secret accessor (view and read secret contents)
    2. secret manager viewer (list secrets)
    3. secret manager admin (create and update secrets and versions)

Author: nicococo|mlox
"""

import os
import json
import yaml

from typing import Dict, Tuple, List
import logging
from google.oauth2 import service_account
from google.cloud import secretmanager
from google.api_core import exceptions as g_exc

logger = logging.getLogger(__name__)

# Define the credentials
ACCESSOR_AIRFLOW_NAME: str = "AIRFLOW_ACCESSOR_CREDENTIALS"
ACCESSOR_ENV_NAME: str = "FLOW_ACCESSOR_CREDENTIALS"
ACCESSOR_FILE_NAME: str = "keyfile.json"

SECRET_MANAGER_ID: str = os.environ["GCP_SECRET_MANAGER_ID"]  # project id OR number

_secret_cache: Dict[str, Tuple[int, str]] = dict()


def _get_credentials() -> service_account.Credentials:
    """Helper to load GCP credentials from various sources."""
    airflow_value = os.environ.get(ACCESSOR_AIRFLOW_NAME, None)

    if airflow_value is not None:
        logger.info("Using Airflow credentials from variable.")
        credentials = service_account.Credentials.from_service_account_info(
            json.loads(airflow_value)
        )
    else:
        value = os.environ.get(ACCESSOR_ENV_NAME, ACCESSOR_FILE_NAME)
        if not os.path.exists(value):
            raise FileNotFoundError(
                f"Could not find GCP credentials file at '{value}'. "
                f"Searched for env var '{ACCESSOR_ENV_NAME}' and file '{ACCESSOR_FILE_NAME}'."
            )

        logger.info(f"GCP secret manager secret accessor keyfile found ({value}).")
        credentials = service_account.Credentials.from_service_account_file(value)

    if not credentials:
        raise ValueError("Credentials were found but are not valid.")

    return credentials


def read_secret_as_raw_token(secret_name: str, version: str = "latest") -> str | None:
    """Load a raw secret token from gcloud secret manager.

    Args:
        secret_name (str): Name of the google secret manager secret. Only latest version is used.
        version (str): (Optional) The secret version. If not provided then the latest version is used.

    Returns:
        str: - Content of the latest secret as str.
             - None, if some exception occured (e.g. no internet connection)
    """
    if secret_name in _secret_cache:
        _secret_cache[secret_name] = (
            _secret_cache[secret_name][0] + 1,
            _secret_cache[secret_name][1],
        )  # increase usage counter
        return _secret_cache[secret_name][1]

    payload = None
    try:
        credentials = _get_credentials()
        client = secretmanager.SecretManagerServiceClient(credentials=credentials)

        SECRET_PATH_ID = (
            f"projects/{SECRET_MANAGER_ID}/secrets/{secret_name}/versions/{version}"
        )
        response = client.access_secret_version(request={"name": SECRET_PATH_ID})
        payload = response.payload.data.decode("UTF-8")
        _secret_cache[secret_name] = (1, payload)
    except Exception as e:
        logger.error(f"Failed to read secret '{secret_name}': {e}")
    return payload


def list_secrets() -> List[str]:
    """Lists all secret names in the configured GCP project.

    Returns:
        List[str]: A list of secret names, or an empty list on error.
    """
    secret_names: List[str] = []
    try:
        credentials = _get_credentials()
        client = secretmanager.SecretManagerServiceClient(credentials=credentials)

        parent = f"projects/{SECRET_MANAGER_ID}"

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


def save_secret(name: str, secret: Dict) -> bool:
    """Saves a secret to GCP Secret Manager.

    Creates the secret container if it doesn't exist, then adds the
    payload as a new version.

    Args:
        name: The name/ID of the secret.
        secret: The dictionary content to save.

    Returns:
        True if successful, False otherwise.
    """
    try:
        credentials = _get_credentials()
        client = secretmanager.SecretManagerServiceClient(credentials=credentials)
        parent = f"projects/{SECRET_MANAGER_ID}"
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
        payload_bytes = json.dumps(secret, indent=2).encode("UTF-8")

        # Add the secret payload as a new version
        response = client.add_secret_version(
            request={"parent": secret_path, "payload": {"data": payload_bytes}}
        )
        logger.info(f"Added new version to secret '{name}': {response.name}")
        return True

    except Exception as e:
        logger.error(f"Failed to save secret '{name}': {e}")
        return False


def read_secret_as_yaml(secret_name: str) -> Dict:
    """Load yaml from gcloud secret manager.

    Args:
        secret_name (str): Name of the google secret manager secret. Only latest version is used.

    Returns:
        Dict: Content of the latest secret (must have json dictionary form)
    """
    ret = read_secret_as_raw_token(secret_name)
    if ret is None:
        return dict()
    return yaml.safe_load(ret)


def read_secret_as_dict(secret_name: str) -> Dict:
    """Load dictionary from gcloud secret manager.

    Args:
        secret_name (str): Name of the google secret manager secret. Only latest version is used.

    Returns:
        Dict: Content of the latest secret (must have json dictionary form)
    """
    ret = read_secret_as_raw_token(secret_name)
    if ret is None:
        return dict()
    return json.loads(ret)


def read_secret_as_service_account_credentials(
    secret_name: str, scopes: List[str]
) -> service_account.Credentials:
    """Load credentials from Google Cloud Secret Manager using the Google OAuth client.

    Args:
        secret_name (str): Name of the Google Secret Manager secret. Only the latest version is used.
        scopes (List[str]): List of service APIs to use (ignored in this implementation).

    Returns:
        service_account.Credentials: Google service account credential object.
    """
    keyfile_dict = read_secret_as_dict(secret_name)
    return dict_to_service_account_credentials(keyfile_dict, scopes)


def dict_to_service_account_credentials(
    keyfile_dict: Dict, scopes: List
) -> service_account.Credentials:
    """Translates a keyfile dictionary into a service account credential using the Google OAuth client.

    Args:
        keyfile_dict (Dict[str, str]): A dictionary containing service account information.
        scopes (List[str]): A list of scopes for the credentials (not used in this implementation).

    Returns:
        service_account.Credentials: The service account credentials created from the keyfile dictionary.
    """
    logger.info("Using google oauth module (ignoring scopes).")
    return service_account.Credentials.from_service_account_info(keyfile_dict)


def get_secret_usage_statistics() -> Dict:
    """Get a dictionary of used secrets and number of invokes.

    Returns:
        Dict: Dict of secret name and number of invokes
    """
    res = dict()
    for k, v in _secret_cache.items():
        res[k] = v[0]
    return res


if __name__ == "__main__":
    print("Read secret #1: ", read_secret_as_yaml("FLOW_SETTINGS"))
    print("Read secret #2: ", read_secret_as_yaml("FLOW_SETTINGS"))
    print("Read secret #3: ", read_secret_as_yaml("FLOW_SETTINGS"))

    print("\n--- Saving a new or existing secret ---")
    save_success = save_secret("MLOX_TEST_SECRET", {"key": "value", "timestamp": "now"})
    print(f"Save successful: {save_success}")

    print("\n--- Listing all secrets ---")
    print(list_secrets())

    print("Secret stats (#calls): ", get_secret_usage_statistics())
