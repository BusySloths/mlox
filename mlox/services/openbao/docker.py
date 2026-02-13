"""Docker deployment adapter for OpenBao secret management services.

Purpose:
- Stand up OpenBao in containers with TLS setup and service endpoint metadata.

Key public classes/functions:
- ``OpenBaoDockerService``

Expected runtime mode:
- Remote executor (invoked from CLI/UI/TUI orchestration)

Related modules (plain-text links):
- mlox.service
- mlox.services.openbao.ui
- mlox.services.openbao.client
"""

from __future__ import annotations

import logging
import re
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
    mount_path: str = "secret"
    compose_service_names: Dict[str, str] = field(init=False, default_factory=dict)
    service_url: str = field(default="", init=False)
    stack_prefix: str = field(default="", init=False)

    def __post_init__(self) -> None:
        self.port = int(self.port)
        self.state = "un-initialized"

    # ------------------------------------------------------------------
    # AbstractService implementation
    # ------------------------------------------------------------------
    def setup(self, conn) -> None:
        self.exec.fs_create_dir(conn, self.target_path)
        self.exec.fs_copy(
            conn, self.template, f"{self.target_path}/{self.target_docker_script}"
        )

        slug = re.sub(r"[^a-z0-9]+", "_", self.name.lower()).strip("_") or "openbao"
        self.stack_prefix = f"{slug}_{self.uuid[:8]}"

        env_path = f"{self.target_path}/{self.target_docker_env}"
        self.exec.fs_create_empty_file(conn, env_path)
        self.exec.fs_append_line(
            conn, env_path, f"OPENBAO_STACK_PREFIX={self.stack_prefix}"
        )
        self.exec.fs_append_line(conn, env_path, f"OPENBAO_PORT={self.port}")
        self.exec.fs_append_line(
            conn, env_path, f"OPENBAO_ROOT_TOKEN={self.root_token}"
        )
        self.exec.fs_append_line(
            conn, env_path, f"OPENBAO_MOUNT_PATH={self.mount_path}"
        )
        self.exec.fs_append_line(conn, env_path, f"OPENBAO_URL={conn.host}")

        self.compose_service_names = {
            "Traefik": f"{self.stack_prefix}_traefik",
            "OpenBao": f"{self.stack_prefix}_openbao",
        }

        self.service_ports["OpenBao API"] = int(self.port)
        self.service_url = f"https://{conn.host}:{self.port}"
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

            target_name = None
            if isinstance(self.compose_service_names, dict):
                target_name = self.compose_service_names.get("OpenBao")

            for name, state in states.items():
                if not isinstance(name, str):
                    continue

                if target_name:
                    matched = name == target_name or target_name in name
                else:
                    matched = "openbao" in name.lower()

                if matched and isinstance(state, dict):
                    status = state.get("Status") or state.get("State") or "unknown"
                    if isinstance(status, str) and "running" in status.lower():
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
                "verify_tls": False,
            }
        }

    # ------------------------------------------------------------------
    # AbstractSecretManagerService implementation
    # ------------------------------------------------------------------
    def get_secret_manager(self, infra: Infrastructure) -> AbstractSecretManager:
        bundle = infra.get_bundle_by_service(self)
        if bundle is None:
            raise ValueError(
                "OpenBao service is not attached to a bundle in the infrastructure"
            )

        server = bundle.server
        address = f"https://{server.ip}:{self.port}"
        return OpenBaoSecretManager(
            address=address,
            token=self.root_token,
            mount_path=self.mount_path,
        )
