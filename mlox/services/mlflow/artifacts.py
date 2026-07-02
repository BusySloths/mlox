from __future__ import annotations

import json
import os
from typing import Any
from pathlib import Path
from urllib.parse import urlparse

import mlflow  # type: ignore
import urllib3
from mlflow.store.artifact.mlflow_artifacts_repo import MlflowArtifactsRepository
from mlflow.tracking._tracking_service.utils import get_default_host_creds
from mlflow.utils.rest_utils import http_request


DEFAULT_TIMEOUT = 8


def configure_mlflow_client(
    service_url: str,
    username: str,
    password: str,
    *,
    timeout: int = DEFAULT_TIMEOUT,
) -> None:
    mlflow.set_tracking_uri(service_url)
    mlflow.set_registry_uri(service_url)
    os.environ["MLFLOW_TRACKING_USERNAME"] = username
    os.environ["MLFLOW_TRACKING_PASSWORD"] = password
    os.environ["MLFLOW_TRACKING_INSECURE_TLS"] = "true"
    os.environ.setdefault("MLFLOW_HTTP_REQUEST_TIMEOUT", str(timeout))
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


def load_registered_model_json_artifact(
    *,
    service_url: str,
    username: str,
    password: str,
    model_name: str,
    model_version: str,
    artifact_path: str,
    timeout: int = DEFAULT_TIMEOUT,
) -> Any | None:
    configure_mlflow_client(service_url, username, password, timeout=timeout)
    client = mlflow.tracking.MlflowClient()
    root_uri = client.get_model_version_download_uri(model_name, str(model_version))
    artifact_uri = _join_artifact_uri(root_uri, artifact_path, service_url)
    if not artifact_uri:
        return None

    parsed = urlparse(artifact_uri)
    if parsed.scheme in {"http", "https"}:
        root_uri, file_name = artifact_uri.rsplit("/", 1)
        response = http_request(
            get_default_host_creds(root_uri),
            f"/{file_name}",
            "GET",
            timeout=timeout,
            max_retries=0,
        )
        if response.status_code == 404:
            return None
        response.raise_for_status()
        return response.json()

    if parsed.scheme in {"", "file"}:
        path = Path(parsed.path if parsed.scheme == "file" else artifact_uri)
        return json.loads(path.read_text(encoding="utf-8"))

    return None


def _join_artifact_uri(root_uri: str, artifact_path: str, tracking_uri: str) -> str:
    root_uri = root_uri.rstrip("/") + "/"
    parsed = urlparse(root_uri)
    if parsed.scheme == "mlflow-artifacts":
        root_uri = MlflowArtifactsRepository.resolve_uri(root_uri, tracking_uri)
    if urlparse(root_uri).scheme in {"http", "https"}:
        return f"{root_uri.rstrip('/')}/{artifact_path}"
    if urlparse(root_uri).scheme in {"", "file"}:
        return str(Path(urlparse(root_uri).path) / artifact_path)
    return ""
