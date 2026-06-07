"""Virtual connector server implementation.

The connector server is a lightweight, non-physical home for services whose
runtime exists outside of MLOX (for example Google Cloud Secret Manager,
Sheets, BigQuery, or other connector-style integrations). It intentionally does
not provision storage, RAM, SSH, Docker, or Kubernetes resources.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, ClassVar, IO

from mlox.server import (
    AbstractConnectorServer,
    AbstractServer,
    MloxUser,
    ServerCapability,
    ServerConnection,
)
from mlox.utils import generate_password

logger = logging.getLogger(__name__)


class _VirtualCommandResult:
    """Minimal Fabric-like result for no-op virtual commands."""

    def __init__(self, command: str, stdout: str = ""):
        self.command = command
        self.stdout = stdout
        self.stderr = ""
        self.return_code = 0
        self.ok = True


class VirtualConnection:
    """Connection-like no-op object for connector services.

    It provides the small Fabric-compatible surface used by service lifecycle
    methods while avoiding any shell access to a real machine.
    """

    user = "mlox_connector"
    port = 0

    def __init__(self, host: str) -> None:
        self.host = host
        self.is_connected = False

    def open(self) -> "VirtualConnection":
        self.is_connected = True
        return self

    def close(self) -> None:
        self.is_connected = False

    def __enter__(self) -> "VirtualConnection":
        return self.open()

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def run(
        self, command: str, hide: bool = True, pty: bool = False
    ) -> _VirtualCommandResult:
        logger.debug("Ignoring virtual connector command: %s", command)
        stdout = "ok\n" if command.strip() in {"echo ok", "true"} else ""
        return _VirtualCommandResult(command, stdout=stdout)

    def sudo(
        self, command: str, hide: bool = True, pty: bool = False
    ) -> _VirtualCommandResult:
        return self.run(command, hide=hide, pty=pty)

    def put(self, local: str | IO[bytes], remote: str) -> str:
        logger.debug("Ignoring virtual connector put to %s", remote)
        return remote

    def get(self, remote: str, local: str | IO[bytes]) -> str | IO[bytes]:
        logger.debug("Ignoring virtual connector get from %s", remote)
        return local


class VirtualServerConnection(ServerConnection):
    """Context manager returning a :class:`VirtualConnection`."""

    def __init__(self, connection: VirtualConnection):
        self._connection = connection

    def __enter__(self) -> VirtualConnection:
        return self._connection.open()

    def __exit__(self, exc_type, exc, tb) -> None:
        self._connection.close()


@dataclass
class VirtualConnectorServer(AbstractServer, AbstractConnectorServer):
    """Virtual backend for externally hosted connector services."""

    capabilities: ClassVar[set[ServerCapability]] = {ServerCapability.CONNECTOR}

    def __post_init__(self) -> None:
        super().__post_init__()
        if not self.ip:
            self.ip = f"mlox-connector-{generate_password(8).lower()}"
        self.port = "0"
        self.backend = [ServerCapability.CONNECTOR.value]
        self.mlox_user = MloxUser(
            name=self.root or "mlox_connector",
            pw="",
            home="virtual://connector",
            ssh_passphrase="",
        )
        self.state = "running"

    def get_server_connection(
        self, force_root: bool = False
    ) -> VirtualServerConnection:
        return VirtualServerConnection(VirtualConnection(self.ip))

    def test_connection(self) -> bool:
        return True

    def setup(self) -> None:
        self.setup_backend()

    def update(self) -> None:
        logger.info("Skipping update for virtual connector server.")

    def teardown(self) -> None:
        self.teardown_backend()

    def enable_debug_access(self) -> None:
        logger.info("Debug access is not applicable to virtual connector servers.")

    def disable_debug_access(self) -> None:
        logger.info("Debug access is not applicable to virtual connector servers.")

    def setup_backend(self) -> None:
        self.state = "running"
        self.backend = [ServerCapability.CONNECTOR.value]

    def teardown_backend(self) -> None:
        self.state = "shutdown"

    def start_backend_runtime(self) -> None:
        self.state = "running"

    def stop_backend_runtime(self) -> None:
        self.state = "shutdown"

    def get_backend_status(self) -> dict[str, Any]:
        return {
            "backend.is_running": self.state == "running",
            "backend.connector.virtual": True,
        }

    def get_server_info(self, no_cache: bool = False) -> dict[str, str | int | float]:
        return {
            "host": self.ip,
            "cpu_count": 0,
            "ram_gb": 0.0,
            "storage_gb": 0.0,
            "pretty_name": "Virtual connector backend",
        }
