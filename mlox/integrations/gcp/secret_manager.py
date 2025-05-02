"""Provides GCP Secret Manager functions.

To access the secret manager, a service account with secret manager secret accessor roles is mandatory.
For local use, you can download the FLOW_ACCESSOR_CREDENTIALS json dict in secret manager and
    1. either place it as `keyfile.json` in the project root folder
    2. specify the filename and path in env variable FLOW_ACCESSOR_CREDENTIALS:
        e.g. FLOW_ACCESSOR_CREDENTIALS="/path/to/secret-accessor-credentials.json"
    3. set an airflow variable `FLOWPROVIDER_ACCESSOR` containing the json dict contents

Author: nicococo
"""

import os
import json
import yaml

from typing import Dict, Tuple, List
import logging
from google.oauth2 import service_account
from google.cloud import secretmanager

logger = logging.getLogger(__name__)

# Define the credentials
ACCESSOR_AIRFLOW_NAME: str = "AIRFLOW_ACCESSOR_CREDENTIALS"
ACCESSOR_ENV_NAME: str = "FLOW_ACCESSOR_CREDENTIALS"
ACCESSOR_FILE_NAME: str = "keyfile.json"

SECRET_MANAGER_ID: str = os.environ["GCP_SECRET_MANAGER_ID"]

_secret_cache: Dict[str, Tuple[int, str]] = dict()


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

    airflow_value = os.environ.get(ACCESSOR_AIRFLOW_NAME, None)

    if airflow_value is not None:
        logger.info(f"Using Airflow credentials {airflow_value}.")
        credentials = service_account.Credentials.from_service_account_info(
            json.loads(airflow_value)
        )
    else:
        value = os.environ.get(ACCESSOR_ENV_NAME, ACCESSOR_FILE_NAME)
        # Attention: Environment variable GOOGLE_APPLICATION_CREDENTIALS with path to secret-accessor-credentials.json is
        # required to access the secret manager
        assert value is not None, (
            f"Could neither find Airflow credentials, {ACCESSOR_FILE_NAME} in project root, or environment variable {ACCESSOR_ENV_NAME}."
        )
        logger.info(f"GCP secret manager secret accessor keyfile found ({value}).")
        credentials = service_account.Credentials.from_service_account_file(value)

    assert credentials is not None, "Credentials where found but are not valid."

    SECRET_PATH_ID = (
        f"projects/{SECRET_MANAGER_ID}/secrets/{secret_name}/versions/{version}"
    )
    payload = None
    try:
        client = secretmanager.SecretManagerServiceClient(credentials=credentials)
        payload = client.access_secret_version(
            request={"name": SECRET_PATH_ID}
        ).payload.data.decode("UTF-8")
        _secret_cache[secret_name] = (1, payload)
    except BaseException as e:
        logger.error(e)
    return payload


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
    print("Secret stats (#calls): ", get_secret_usage_statistics())
