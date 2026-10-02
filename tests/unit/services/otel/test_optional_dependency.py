"""The deployment adapter must remain usable without the optional OTel SDK."""

from pathlib import Path
import subprocess
import sys


def test_docker_adapter_import_does_not_require_opentelemetry_sdk():
    repository_root = Path(__file__).resolve().parents[4]
    script = """
import builtins

original_import = builtins.__import__


def reject_opentelemetry(name, *args, **kwargs):
    if name == "opentelemetry" or name.startswith("opentelemetry."):
        raise ModuleNotFoundError("OpenTelemetry SDK intentionally unavailable")
    return original_import(name, *args, **kwargs)


builtins.__import__ = reject_opentelemetry
from mlox.services.otel.docker import OtelDockerService

assert OtelDockerService.__name__ == "OtelDockerService"
"""

    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=repository_root,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
