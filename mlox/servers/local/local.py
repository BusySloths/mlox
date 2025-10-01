"""Localhost server implementation for development and testing.

This module provides a lightweight server backend that executes all
operations on the current machine without relying on SSH connectivity.
It is intended for local development workflows on macOS and Linux and
focuses on minimal setup by reusing the existing command execution
helpers.
"""

from __future__ import annotations

import getpass
import logging
import os
import platform
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, IO

from mlox.server import (
    AbstractGitServer,
    AbstractServer,
    MloxUser,
    ServerConnection,
)


logger = logging.getLogger(__name__)


class _LocalCommandResult:
    """Minimal result object mimicking Fabric's command result."""

    def __init__(self, command: str, completed: subprocess.CompletedProcess[str]):
        self.command = command
        self.stdout = completed.stdout or ""
        self.stderr = completed.stderr or ""
        self.return_code = completed.returncode
        self.ok = completed.returncode == 0


class LocalConnection:
    """Connection-like object executing commands on the local machine."""

    def __init__(self, base_path: Path, host: str, user: str):
        self.base_path = base_path
        self.host = host
        self.user = user
        self.port = 0
        self.is_connected = False

    # Context management -------------------------------------------------
    def open(self) -> "LocalConnection":
        self.is_connected = True
        return self

    def close(self) -> None:
        self.is_connected = False

    def __enter__(self) -> "LocalConnection":
        return self.open()

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    # Command helpers ----------------------------------------------------
    def run(
        self, command: str, hide: bool = True, pty: bool = False
    ) -> _LocalCommandResult:
        return self._execute(command)

    def sudo(
        self, command: str, hide: bool = True, pty: bool = False
    ) -> _LocalCommandResult:
        sudo_path = shutil.which("sudo")
        if sudo_path:
            sudo_command = f"{sudo_path} -n {command}"
            result = self._execute(sudo_command)
            if result.return_code == 0:
                return result
            if "password" not in result.stderr.lower():
                return result
            logger.debug(
                "sudo command failed due to password prompt; retrying without sudo: %s",
                command,
            )
        return self._execute(command)

    def _execute(self, command: str) -> _LocalCommandResult:
        completed = subprocess.run(
            command,
            shell=True,
            cwd=self.base_path,
            capture_output=True,
            text=True,
        )
        if completed.returncode != 0:
            logger.debug(
                "Local command '%s' failed with exit code %s: %s",
                command,
                completed.returncode,
                completed.stderr.strip(),
            )
            # Match Fabric semantics: raise on failure
            raise RuntimeError(
                f"Local command '{command}' failed with exit code {completed.returncode}: {completed.stderr.strip()}"
            )
        return _LocalCommandResult(command, completed)

    # File transfer helpers ---------------------------------------------
    def put(self, local: str | os.PathLike[str] | IO[bytes], remote: str) -> Path:
        destination = Path(remote)
        destination.parent.mkdir(parents=True, exist_ok=True)

        if hasattr(local, "read"):
            data = local.read()
            if isinstance(data, str):
                data_bytes = data.encode()
            else:
                data_bytes = data
            with open(destination, "wb") as fh:
                fh.write(data_bytes)
        else:
            shutil.copy2(Path(local), destination)

        return destination

    def get(
        self, remote: str, local: str | os.PathLike[str] | IO[bytes]
    ) -> str | IO[bytes]:
        source = Path(remote)
        if hasattr(local, "write"):
            local.write(source.read_bytes())
            if hasattr(local, "seek"):
                local.seek(0)
            return local

        destination = Path(local)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        return str(destination)


class LocalServerConnection(ServerConnection):
    """Context manager returning a :class:`LocalConnection`."""

    def __init__(self, connection: LocalConnection):
        self._connection = connection

    def __enter__(self) -> LocalConnection:
        return self._connection.open()

    def __exit__(self, exc_type, exc, tb) -> None:
        self._connection.close()


@dataclass
class LocalhostServer(AbstractServer, AbstractGitServer):
    """A server representation that targets the local machine."""

    docker_available: bool = field(default=False, init=False)
    base_path: str = field(default_factory=lambda: str(Path.cwd()), init=False)

    def __post_init__(self) -> None:
        super().__post_init__()
        if not self.ip:
            self.ip = "127.0.0.1"
        self.port = "0"

        current_user = getpass.getuser()
        self.root = current_user or self.root
        self.mlox_user = MloxUser(
            name=current_user,
            pw="",
            home=str(self.base_path),
            ssh_passphrase="",
        )
        self.backend = ["local"]
        self.docker_available = self._detect_docker()
        if self.docker_available:
            self.backend.append("docker")

    # Connection helpers -------------------------------------------------
    def get_server_connection(self, force_root: bool = False) -> LocalServerConnection:
        if not self.mlox_user:
            raise ValueError("Mlox user must be defined to establish a connection.")
        connection = LocalConnection(
            self.base_path, host=self.ip, user=self.mlox_user.name
        )
        return LocalServerConnection(connection)

    def test_connection(self) -> bool:  # pragma: no cover - exercised indirectly
        try:
            with self.get_server_connection() as conn:
                result = conn.run("echo ok")
                return result.return_code == 0
        except Exception as exc:  # pragma: no cover - defensive
            logger.error("Failed to verify local connection: %s", exc)
            return False

    # Lifecycle ---------------------------------------------------------
    def setup(self) -> None:
        if self.state != "un-initialized":
            logger.error("Cannot initialize an already initialized server.")
            return
        self.state = "starting"
        self.setup_backend()

    def update(self) -> None:
        logger.info("Skipping update for LocalhostServer.")

    def teardown(self) -> None:
        self.state = "shutdown"
        self.teardown_backend()

    def enable_debug_access(self) -> None:
        logger.info("Debug access is always available on localhost.")

    def disable_debug_access(self) -> None:
        logger.info("Debug access cannot be disabled for localhost.")

    # Backend -----------------------------------------------------------
    def setup_backend(self) -> None:
        self.state = "running"
        self.docker_available = self._detect_docker()
        logger.info(
            "Localhost backend ready (docker available=%s)", self.docker_available
        )

    def teardown_backend(self) -> None:
        self.state = "no-backend"
        logger.info("Localhost backend stopped.")

    def start_backend_runtime(self) -> None:
        logger.info("Local backend start requested.")

    def stop_backend_runtime(self) -> None:
        logger.info("Local backend stop requested.")

    def get_backend_status(self) -> dict[str, Any]:
        return {
            "backend.is_running": self.state == "running",
            "backend.docker.available": self.docker_available,
        }

    # Git ---------------------------------------------------------------
    def git_clone(self, repo_url: str, path: str) -> None:
        destination = Path(path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(["git", "clone", repo_url, str(destination)], check=True)

    def git_pull(self, path: str) -> None:
        subprocess.run(["git", "-C", path, "pull"], check=True)

    def git_remove(self, path: str) -> None:
        shutil.rmtree(path, ignore_errors=True)

    # Metadata ----------------------------------------------------------
    def get_server_info(self, no_cache: bool = False) -> dict[str, Any]:
        cpu_count = os.cpu_count() or 0
        ram_gb = self._get_memory_gb()
        storage = shutil.disk_usage(self.base_path)
        pretty_name = platform.platform()
        return {
            "host": self.ip,
            "cpu_count": cpu_count,
            "ram_gb": ram_gb,
            "storage_gb": round(storage.total / (1024**3), 2),
            "pretty_name": pretty_name,
        }

    # Helpers -----------------------------------------------------------
    def _detect_docker(self) -> bool:
        docker_path = shutil.which("docker")
        if not docker_path:
            return False
        result = subprocess.run(
            [docker_path, "info"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return result.returncode == 0

    def _get_memory_gb(self) -> float:
        if hasattr(os, "sysconf"):
            if (
                "SC_PAGE_SIZE" in os.sysconf_names
                and "SC_PHYS_PAGES" in os.sysconf_names
            ):
                page_size = os.sysconf("SC_PAGE_SIZE")
                phys_pages = os.sysconf("SC_PHYS_PAGES")
                if page_size > 0 and phys_pages > 0:
                    return round(page_size * phys_pages / (1024**3), 2)
        logger.debug("Falling back to 0 for memory detection on unsupported platform.")
        return 0.0
