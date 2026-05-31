from __future__ import annotations

import json
import logging
import shutil
import socket
import subprocess
import time
import uuid

from dataclasses import dataclass
from importlib import resources
from pathlib import Path
from typing import Any, ClassVar, Dict

from mlox.server import ServerCapability
from mlox.servers.ubuntu.docker import UbuntuDockerServer
from mlox.servers.ubuntu.k3s import UbuntuK3sServer
from mlox.servers.ubuntu.native import UbuntuNativeServer

logger = logging.getLogger(__name__)

try:  # pragma: no cover - optional integration dependency
    from multipass import MultipassClient  # type: ignore

    _HAS_MULTIPASS_SDK = True
except Exception:  # pragma: no cover - optional integration dependency
    MultipassClient = None  # type: ignore
    _HAS_MULTIPASS_SDK = False


def _coerce_positive_int(value: str | int, default: int) -> int:
    try:
        coerced = int(value)
        return coerced if coerced > 0 else default
    except (TypeError, ValueError):
        return default


@dataclass
class MultipassUbuntuServerMixin:
    """Mixin that manages the Ubuntu VM lifecycle with Multipass.

    The concrete classes inherit from the existing Ubuntu native, Docker, and K3s
    server implementations. Multipass is only responsible for creating and
    removing a reachable Ubuntu VM; once SSH is available the normal Ubuntu setup
    flow provisions users and backends exactly like a manually supplied server.
    """

    vm_name: str = ""
    cpus: str = "2"
    memory: str = "4G"
    disk: str = "20G"
    image: str = "24.04"
    cloud_init: str = ""
    launch_timeout: str = "600"

    def __post_init__(self) -> None:
        super().__post_init__()  # type: ignore[misc]
        if not self.vm_name:
            self.vm_name = f"mlox-{uuid.uuid4().hex[:8]}"
        if not self.ip:
            self.ip = self.vm_name

    @property
    def is_multipass_available(self) -> bool:
        return _HAS_MULTIPASS_SDK or shutil.which("multipass") is not None

    def test_connection(self) -> bool:
        if self.ip and self.ip != self.vm_name:
            return super().test_connection()  # type: ignore[misc]
        available = self.is_multipass_available
        if not available:
            logger.warning("Multipass is not available; cannot launch %s.", self.vm_name)
        return available

    def setup(self) -> None:
        if self.state != "un-initialized":
            logging.error("Can not initialize an already initialized server.")
            return
        launched = False
        try:
            self.launch_vm()
            launched = True
            super().setup()  # type: ignore[misc]
        except Exception:
            self.state = "un-initialized"
            if launched:
                self.delete_vm()
                self.ip = self.vm_name
            raise

    def teardown(self) -> None:
        try:
            if self.ip and self.ip != self.vm_name and self.state == "running":
                super().teardown()  # type: ignore[misc]
        finally:
            self.delete_vm()
            self.state = "shutdown"

    def start_vm(self) -> None:
        if self._run_multipass_vm_action("start"):
            self.ip = self.wait_for_ssh()
            self.state = "running"
            return
        self._run_multipass_cli(["start", self.vm_name])
        self.ip = self.wait_for_ssh()
        self.state = "running"

    def stop_vm(self) -> None:
        if self._run_multipass_vm_action("stop"):
            self.state = "stopped"
            return
        self._run_multipass_cli(["stop", self.vm_name])
        self.state = "stopped"

    def _run_multipass_vm_action(self, action: str) -> bool:
        if not _HAS_MULTIPASS_SDK:
            return False

        client = MultipassClient()
        vm = getattr(self, "_multipass_vm", None)
        if vm is None and hasattr(client, "find"):
            try:
                vm = client.find(self.vm_name)
            except Exception:
                logger.debug(
                    "Could not find Multipass VM %s via SDK.",
                    self.vm_name,
                    exc_info=True,
                )

        if vm is not None and hasattr(vm, action):
            getattr(vm, action)()
            return True

        if hasattr(client, action):
            getattr(client, action)(self.vm_name)
            return True

        return False

    def launch_vm(self) -> None:
        if not self.is_multipass_available:
            raise RuntimeError("Multipass is not installed or not available on PATH.")

        cloud_init_path = self._resolve_cloud_init_path()
        logger.info(
            "Launching Multipass VM %s image=%s cpus=%s memory=%s disk=%s cloud_init=%s",
            self.vm_name,
            self.image,
            self.cpus,
            self.memory,
            self.disk,
            cloud_init_path,
        )
        if _HAS_MULTIPASS_SDK:
            client = MultipassClient()
            launch_kwargs = {
                "vm_name": self.vm_name,
                "cpu": _coerce_positive_int(self.cpus, 2),
                "disk": self.disk,
                "mem": self.memory,
                "cloud_init": str(cloud_init_path) if cloud_init_path else None,
            }
            try:
                self._multipass_vm = client.launch(
                    image=self.image, **launch_kwargs
                )
            except TypeError:
                self._multipass_vm = client.launch(**launch_kwargs)
        else:
            cmd = [
                "launch",
                self.image,
                "--name",
                self.vm_name,
                "--cpus",
                str(_coerce_positive_int(self.cpus, 2)),
                "--memory",
                self.memory,
                "--disk",
                self.disk,
            ]
            if cloud_init_path:
                cmd.extend(["--cloud-init", str(cloud_init_path)])
            self._run_multipass_cli(cmd)

        self.ip = self.wait_for_ssh()
        self.wait_for_root_login()
        logger.info("Multipass VM %s is reachable at %s", self.vm_name, self.ip)

    def delete_vm(self) -> None:
        if not self.is_multipass_available:
            logger.warning("Multipass unavailable; cannot delete VM %s.", self.vm_name)
            return
        logger.info("Deleting Multipass VM %s", self.vm_name)
        try:
            if _HAS_MULTIPASS_SDK:
                client = MultipassClient()
                vm = getattr(self, "_multipass_vm", None)
                try:
                    if vm is not None:
                        vm.delete()
                    elif hasattr(client, "find"):
                        client.find(self.vm_name).delete()
                    else:
                        client.delete(self.vm_name)
                except AttributeError:
                    client.delete(self.vm_name)
                try:
                    client.purge()
                except Exception:
                    logger.debug("Multipass purge failed or is unsupported.", exc_info=True)
            else:
                self._run_multipass_cli(["delete", self.vm_name], check=False)
                self._run_multipass_cli(["purge"], check=False)
        except Exception as exc:  # pragma: no cover - best effort cleanup
            logger.warning("Could not delete Multipass VM %s: %s", self.vm_name, exc)

    def get_backend_status(self) -> Dict[str, Any]:
        backend_info = super().get_backend_status()  # type: ignore[misc]
        backend_info["multipass.vm_name"] = self.vm_name
        backend_info["multipass.ip"] = self.ip
        backend_info["multipass.cpus"] = self.cpus
        backend_info["multipass.memory"] = self.memory
        backend_info["multipass.disk"] = self.disk
        try:
            backend_info["multipass.info"] = self.multipass_info()
        except Exception as exc:
            backend_info["multipass.info"] = f"Error retrieving Multipass info: {exc}"
        return backend_info

    def multipass_info(self) -> Dict[str, Any]:
        if _HAS_MULTIPASS_SDK:
            vm = getattr(self, "_multipass_vm", None)
            if vm is not None:
                info = vm.info()
                return info if isinstance(info, dict) else {"raw": info}
            if shutil.which("multipass") is None:
                client = MultipassClient()
                if hasattr(client, "find"):
                    info = client.find(self.vm_name).info()
                    return info if isinstance(info, dict) else {"raw": info}
        raw = self._run_multipass_cli(
            ["info", self.vm_name, "--format", "json"], capture_output=True
        )
        try:
            parsed = json.loads(raw)
            return parsed if isinstance(parsed, dict) else {"raw": parsed}
        except json.JSONDecodeError:
            return {"raw": raw}

    def wait_for_ssh(self) -> str:
        timeout = _coerce_positive_int(self.launch_timeout, 600)
        deadline = time.time() + timeout
        last_exc: Exception | None = None
        while time.time() < deadline:
            try:
                ip = self._current_ipv4()
                if ip and self._is_ssh_reachable(ip):
                    return ip
            except Exception as exc:
                last_exc = exc
            time.sleep(3)
        raise TimeoutError(
            f"VM {self.vm_name} SSH not reachable after {timeout}s. Last error: {last_exc!r}"
        )

    def wait_for_root_login(self) -> None:
        timeout = _coerce_positive_int(self.launch_timeout, 600)
        deadline = time.time() + timeout
        last_exc: Exception | None = None
        while time.time() < deadline:
            try:
                with self.get_server_connection(force_root=True) as conn:
                    result = conn.run(
                        "true",
                        hide=True,
                        warn=True,
                        pty=False,
                    )
                    if result.ok:
                        return
                    output = (result.stderr or result.stdout or "").strip()
                    last_exc = RuntimeError(output or f"exit code {result.exited}")
            except Exception as exc:
                last_exc = exc
            time.sleep(3)
        raise TimeoutError(
            f"VM {self.vm_name} root SSH login not ready after {timeout}s. Last error: {last_exc!r}"
        )

    def _current_ipv4(self) -> str | None:
        info = self.multipass_info()
        data: Any = info.get("info", {}).get(self.vm_name, info)
        if isinstance(data, dict):
            ipv4 = data.get("ipv4")
            if isinstance(ipv4, list):
                return next((ip for ip in ipv4 if isinstance(ip, str) and ip), None)
            if isinstance(ipv4, str) and ipv4:
                return ipv4
        return None

    def _is_ssh_reachable(self, ip: str) -> bool:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(3.0)
        try:
            return sock.connect_ex((ip, int(self.port))) == 0
        finally:
            sock.close()

    def _resolve_cloud_init_path(self) -> Path | None:
        if self.cloud_init:
            return Path(self.cloud_init).expanduser().resolve()
        try:
            with resources.as_file(
                resources.files("mlox.servers.ubuntu").joinpath(
                    "cloud-init-multipass.yaml"
                )
            ) as path:
                return Path(path)
        except Exception:
            root_cloud_init = Path(__file__).resolve().parents[3] / "cloud-init.yaml"
            return root_cloud_init if root_cloud_init.exists() else None

    def _run_multipass_cli(
        self,
        args: list[str],
        *,
        capture_output: bool = False,
        check: bool = True,
    ) -> str:
        completed = subprocess.run(
            ["multipass", *args],
            check=check,
            text=True,
            capture_output=True,
        )
        if capture_output:
            return completed.stdout
        return completed.stdout


@dataclass
class MultipassUbuntuNativeServer(MultipassUbuntuServerMixin, UbuntuNativeServer):
    capabilities: ClassVar[set[ServerCapability]] = UbuntuNativeServer.capabilities


@dataclass
class MultipassUbuntuDockerServer(MultipassUbuntuServerMixin, UbuntuDockerServer):
    capabilities: ClassVar[set[ServerCapability]] = UbuntuDockerServer.capabilities


@dataclass
class MultipassUbuntuK3sServer(MultipassUbuntuServerMixin, UbuntuK3sServer):
    capabilities: ClassVar[set[ServerCapability]] = UbuntuK3sServer.capabilities
