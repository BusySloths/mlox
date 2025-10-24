"""Docker-based OpenBao secret manager service."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Dict

from mlox.infra import Infrastructure
from mlox.secret_manager import AbstractSecretManager, AbstractSecretManagerService
from mlox.service import AbstractService
from .client import OpenBaoSecretManager

logger = logging.getLogger(__name__)


@dataclass
class OpenBaoDockerService(AbstractService, AbstractSecretManagerService):
    """Deploy OpenBao via Docker compose and expose a secret manager client."""

    root_token: str
    port: int | str
    server_uuid: str | None
    mount_path: str = "secret"
    scheme: str = "https"
    verify_tls: bool = False
    compose_service_names: Dict[str, str] = field(
        default_factory=lambda: {"Traefik": "traefik", "OpenBao": "openbao"},
        init=False,
    )
    service_url: str = field(default="", init=False)

    def __post_init__(self) -> None:
        self.port = int(self.port)
        if self.server_uuid in ("", "None"):
            self.server_uuid = None
        self.scheme = (self.scheme or "https").lower()
        self.verify_tls = bool(self.verify_tls)
        self.state = "un-initialized"

    # ------------------------------------------------------------------
    # AbstractService implementation
    # ------------------------------------------------------------------
    def setup(self, conn) -> None:
        self.exec.fs_create_dir(conn, self.target_path)
        self.exec.fs_copy(
            conn, self.template, f"{self.target_path}/{self.target_docker_script}"
        )

        env_path = f"{self.target_path}/{self.target_docker_env}"
        self.exec.fs_create_empty_file(conn, env_path)
        self.exec.fs_append_line(conn, env_path, f"OPENBAO_PORT={self.port}")
        self.exec.fs_append_line(conn, env_path, f"OPENBAO_ROOT_TOKEN={self.root_token}")
        self.exec.fs_append_line(conn, env_path, f"OPENBAO_MOUNT_PATH={self.mount_path}")
        self.exec.fs_append_line(conn, env_path, f"OPENBAO_URL={conn.host}")

        self.service_ports["OpenBao API"] = int(self.port)
        self.service_url = f"{self.scheme}://{conn.host}:{self.port}"
        self.service_urls["OpenBao API"] = self.service_url
        self.state = "stopped"

    def teardown(self, conn) -> None:
        try:
            self.exec.docker_down(
                conn,
                f"{self.target_path}/{self.target_docker_script}",
                remove_volumes=True,
            )
        except Exception as exc:  # pragma: no cover - best-effort cleanup
            logger.warning("Failed to stop OpenBao docker stack: %s", exc)
        self.exec.fs_delete_dir(conn, self.target_path)
        self.state = "un-initialized"

    def spin_up(self, conn) -> bool:
        result = self.compose_up(conn)
        self.state = "running" if result else "unknown"
        return result

    def spin_down(self, conn) -> bool:
        result = self.compose_down(conn, remove_volumes=True)
        self.state = "stopped" if result else "unknown"
        return result

    def check(self, conn) -> Dict:
        try:
            states = self.exec.docker_all_service_states(conn)
            if not states:
                self.state = "stopped"
                return {"status": "stopped"}
            for name, state in states.items():
                if "openbao" in name and isinstance(state, dict):
                    status = state.get("Status") or state.get("State") or "unknown"
                    if "running" in status:
                        self.state = "running"
                        return {"status": "running"}
            self.state = "stopped"
            return {"status": "stopped"}
        except Exception as exc:  # pragma: no cover - defensive logging path
            logger.error("Error checking OpenBao service status: %s", exc)
            self.state = "unknown"
            return {"status": "unknown", "error": str(exc)}

    def get_secrets(self) -> Dict[str, Dict]:
        if not self.root_token:
            return {}
        return {
            "openbao_root_credentials": {
                "token": self.root_token,
                "address": self.service_url,
                "mount_path": self.mount_path,
                "verify_tls": self.verify_tls,
            }
        }

    # ------------------------------------------------------------------
    # AbstractSecretManagerService implementation
    # ------------------------------------------------------------------
    def get_secret_manager(self, infra: Infrastructure) -> AbstractSecretManager:
        if self.server_uuid is None and infra.bundles:
            self.server_uuid = infra.bundles[0].server.uuid

        if not self.server_uuid:
            raise ValueError("Server UUID is not set for OpenBao service")

        server = infra.get_server_by_uuid(self.server_uuid)
        if server is None:
            raise ValueError(
                f"Server with UUID {self.server_uuid} not found in infrastructure."
            )

        address = f"{self.scheme}://{server.ip}:{self.port}"
        secret_manager = OpenBaoSecretManager(
            address=address,
            token=self.root_token,
            mount_path=self.mount_path,
            verify_tls=self.verify_tls,
        )
        return secret_manager
