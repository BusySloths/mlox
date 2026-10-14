"""Deployment adapters must load without their optional client SDKs."""

from pathlib import Path
import subprocess
import sys


def test_deployment_adapter_imports_do_not_require_optional_sdks():
    repository_root = Path(__file__).resolve().parents[4]
    script = """
import builtins

original_import = builtins.__import__


def reject_optional_sdk(name, *args, **kwargs):
    blocked = ("google", "gspread", "mlflow", "numpy", "opentelemetry", "pandas")
    if any(name == package or name.startswith(f"{package}.") for package in blocked):
        raise ModuleNotFoundError(f"Optional SDK {name!r} intentionally unavailable")
    return original_import(name, *args, **kwargs)


builtins.__import__ = reject_optional_sdk
from mlox.services.otel.docker import OtelDockerService
from mlox.services.mlflow.docker import MLFlowDockerService
from mlox.services.mlflow.docker_mlflow3 import MLFlow3DockerService
from mlox.services.gcp.bq_service import GCPBigQueryService
from mlox.services.gcp.secret_service import GCPSecretService
from mlox.services.gcp.sheet_service import GCPSpreadsheetsService
from mlox.services.gcp.storage_service import GCPStorageService

assert OtelDockerService.__name__ == "OtelDockerService"
assert MLFlowDockerService.__name__ == "MLFlowDockerService"
assert MLFlow3DockerService.__name__ == "MLFlow3DockerService"
assert GCPBigQueryService.__name__ == "GCPBigQueryService"
assert GCPSecretService.__name__ == "GCPSecretService"
assert GCPSpreadsheetsService.__name__ == "GCPSpreadsheetsService"
assert GCPStorageService.__name__ == "GCPStorageService"
"""

    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=repository_root,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
