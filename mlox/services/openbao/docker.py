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
import json
import re
from datetime import datetime, timezone
import shlex
import time
from dataclasses import dataclass, field
from typing import Any, Dict

from mlox.execution.base import TaskGroup
from mlox.infra import Infrastructure
from mlox.secret_manager import AbstractSecretManager, AbstractSecretManagerService
from mlox.service import AbstractService
from .client import OpenBaoSecretManager
from mlox.utils import generate_password

logger = logging.getLogger(__name__)


@dataclass
class OpenBaoDockerService(AbstractService, AbstractSecretManagerService):
    """Deploy OpenBao via Docker compose and expose a secret manager client."""

    port: int | str
    mount_path: str = "secret"
    root_token: str = ""
    key_shares: int = 1
    key_threshold: int = 1
    userpass_path: str = "userpass"
    admin_username: str = "mlox-admin"
    admin_password: str = ""
    kv_policy_name: str = "mlox-kv-rw"
    ui_policy_name: str = "mlox-ui-kv-admin"
    client_token: str = ""
    client_token_accessor: str = ""
    client_token_ttl: str = "24h"
    client_token_max_ttl: str = "168h"
    client_token_lease_duration: int = 0
    client_token_renewable: bool = True
    client_token_last_renewed_at: str = ""
    compose_service_names: Dict[str, str] = field(init=False, default_factory=dict)
    unseal_keys: list[str] = field(default_factory=list)
    service_url: str = ""
    stack_prefix: str = ""

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
        data_path = f"{self.target_path}/data"
        logs_path = f"{self.target_path}/logs"
        config_dir = f"{self.target_path}/config"
        self.exec.fs_create_dir(conn, data_path)
        self.exec.fs_create_dir(conn, logs_path)
        self.exec.fs_create_dir(conn, config_dir)
        self.exec.fs_set_permissions(conn, data_path, "777")
        self.exec.fs_set_permissions(conn, logs_path, "777")
        self.exec.tls_setup(conn, conn.host, self.target_path)
        self.exec.fs_set_permissions(conn, f"{self.target_path}/cert.pem", "644")
        self.exec.fs_set_permissions(conn, f"{self.target_path}/key.pem", "644")

        slug = re.sub(r"[^a-z0-9]+", "_", self.name.lower()).strip("_") or "openbao"
        self.stack_prefix = f"{slug}_{self.uuid[:8]}"

        env_path = f"{self.target_path}/{self.target_docker_env}"
        self.exec.fs_create_empty_file(conn, env_path)
        self.exec.fs_append_line(
            conn, env_path, f"OPENBAO_STACK_PREFIX={self.stack_prefix}"
        )
        self.exec.fs_append_line(conn, env_path, f"OPENBAO_PORT={self.port}")
        self.exec.fs_append_line(
            conn, env_path, f"OPENBAO_MOUNT_PATH={self.mount_path}"
        )
        self.exec.fs_append_line(conn, env_path, f"OPENBAO_URL={conn.host}")

        config_path = f"{config_dir}/openbao.hcl"
        self.exec.fs_write_file(conn, config_path, self._render_config(conn.host))

        self.compose_service_names = {
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
        logger.info("Starting OpenBao docker compose stack at %s.", self.target_path)
        result = self._compose_up_with_timeout(conn)
        logger.info("OpenBao docker compose stack command completed.")
        if result:
            logger.info("Bootstrapping OpenBao production instance.")
            self._bootstrap_openbao(conn)
            self._configure_mlox_access(conn)
            logger.info("OpenBao bootstrap completed.")
        self.state = "running" if result else "unknown"
        return result

    def spin_down(self, conn) -> bool:
        result = self.compose_down(conn, remove_volumes=False)
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
        if not self.client_token:
            return {}
        return {
            "openbao_client_credentials": {
                "token": self.client_token,
                "address": self.service_url,
                "mount_path": self.mount_path,
                "verify_tls": False,
                "renewable": self.client_token_renewable,
                "lease_duration": self.client_token_lease_duration,
                "token_accessor": self.client_token_accessor,
            }
        }

    # ------------------------------------------------------------------
    # AbstractSecretManagerService implementation
    # ------------------------------------------------------------------
    def get_secret_manager(
        self, infra: Infrastructure | None = None
    ) -> AbstractSecretManager:
        address = self.service_url
        if infra is not None:
            bundle = infra.get_bundle_by_service(self)
            if bundle is None:
                raise ValueError(
                    "OpenBao service is not attached to a bundle in the infrastructure"
                )
            address = f"https://{bundle.server.ip}:{self.port}"
        if not address:
            raise ValueError("OpenBao service URL is not configured.")

        token = self.client_token or self.root_token
        if not token:
            raise ValueError("OpenBao client token is not configured.")
        return OpenBaoSecretManager(
            address=address,
            token=token,
            mount_path=self.mount_path,
            unseal_keys=list(self.unseal_keys),
        )

    def get_root_secret_manager(
        self, infra: Infrastructure | None = None
    ) -> OpenBaoSecretManager:
        """Return a bootstrap/recovery client that uses the root token."""

        address = self.service_url
        if infra is not None:
            bundle = infra.get_bundle_by_service(self)
            if bundle is None:
                raise ValueError(
                    "OpenBao service is not attached to a bundle in the infrastructure"
                )
            address = f"https://{bundle.server.ip}:{self.port}"
        if not address:
            raise ValueError("OpenBao service URL is not configured.")
        if not self.root_token:
            raise ValueError("OpenBao root token is not configured.")
        return OpenBaoSecretManager(
            address=address,
            token=self.root_token,
            mount_path=self.mount_path,
            unseal_keys=list(self.unseal_keys),
        )

    def renew_client_token(
        self, infra: Infrastructure | None = None, increment: str | int | None = None
    ) -> Dict[str, Any]:
        """Renew the scoped mlox client token and update stored metadata."""

        manager = self.get_secret_manager(infra)
        auth = manager.renew_self(increment or self.client_token_ttl)
        self._store_client_token_auth(auth)
        return auth

    def rotate_client_token(self, infra: Infrastructure | None = None) -> Dict[str, Any]:
        """Create a replacement scoped mlox client token using the root token."""

        manager = self.get_root_secret_manager(infra)
        auth = self._create_client_token(manager)
        self._store_client_token_auth(auth)
        return auth

    def _render_config(self, host: str) -> str:
        node_id = f"mlox-openbao-{self.uuid[:8]}"
        api_addr = f"https://{host}:{self.port}"
        return f"""ui = true
disable_mlock = true
api_addr = "{api_addr}"
cluster_addr = "http://openbao:8201"

storage "raft" {{
  path = "/openbao/data"
  node_id = "{node_id}"
}}

listener "tcp" {{
  address = "0.0.0.0:8200"
  cluster_address = "0.0.0.0:8201"
  tls_disable = false
  tls_cert_file = "/openbao/tls/cert.pem"
  tls_key_file = "/openbao/tls/key.pem"
}}
"""

    def _root_api_client(self, conn) -> OpenBaoSecretManager:
        address = self.service_url or f"https://{conn.host}:{self.port}"
        return OpenBaoSecretManager(
            address=address,
            token=self.root_token,
            mount_path=self.mount_path,
            unseal_keys=list(self.unseal_keys),
        )

    def _render_kv_policy(self) -> str:
        mount = self.mount_path.strip("/") or "secret"
        return f'''path "{mount}/data/*" {{
  capabilities = ["create", "update", "read", "patch"]
}}

path "{mount}/metadata" {{
  capabilities = ["list", "read"]
}}

path "{mount}/metadata/*" {{
  capabilities = ["list", "read"]
}}
'''

    def _render_ui_policy(self) -> str:
        mount = self.mount_path.strip("/") or "secret"
        return f'''path "{mount}/data/*" {{
  capabilities = ["create", "update", "read", "patch", "delete"]
}}

path "{mount}/metadata" {{
  capabilities = ["list", "read", "delete"]
}}

path "{mount}/metadata/*" {{
  capabilities = ["list", "read", "delete"]
}}

path "sys/internal/ui/mounts" {{
  capabilities = ["read"]
}}

path "sys/internal/ui/mounts/*" {{
  capabilities = ["read"]
}}
'''

    def _configure_mlox_access(self, conn) -> None:
        if not self.root_token:
            raise RuntimeError("OpenBao root token is required for mlox access setup.")

        manager = self._root_api_client(conn)
        logger.info("Ensuring OpenBao KV v2 mount '%s' exists via API.", self.mount_path)
        manager.ensure_kv_v2(self.mount_path)
        logger.info("Ensuring OpenBao file audit device exists via API.")
        manager.enable_file_audit()
        logger.info("Writing OpenBao mlox policies.")
        manager.write_policy(self.kv_policy_name, self._render_kv_policy())
        manager.write_policy(self.ui_policy_name, self._render_ui_policy())
        logger.info("Ensuring OpenBao userpass auth is configured.")
        manager.ensure_userpass_auth(self.userpass_path)
        if not self.admin_password:
            self.admin_password = generate_password(length=24, with_punctuation=False)
        manager.create_or_update_userpass_user(
            self.admin_username,
            self.admin_password,
            policies=[self.ui_policy_name],
            ttl="8h",
            max_ttl="24h",
            path=self.userpass_path,
        )
        if not self._client_token_is_valid(manager):
            logger.info("Creating scoped OpenBao client token for mlox.")
            self._store_client_token_auth(self._create_client_token(manager))

    def _client_token_is_valid(self, manager: OpenBaoSecretManager) -> bool:
        if not self.client_token:
            return False
        try:
            token_data = manager.lookup_token(self.client_token)
        except Exception as exc:  # pragma: no cover - defensive OpenBao path
            logger.info("Existing OpenBao client token is not valid: %s", exc)
            return False
        ttl = int(token_data.get("ttl") or 0)
        if ttl <= 0:
            return False
        self.client_token_accessor = str(
            token_data.get("accessor") or self.client_token_accessor or ""
        )
        self.client_token_lease_duration = ttl
        self.client_token_renewable = bool(token_data.get("renewable", True))
        return True

    def _create_client_token(self, manager: OpenBaoSecretManager) -> Dict[str, Any]:
        return manager.create_token(
            ttl=self.client_token_ttl,
            policies=[self.kv_policy_name],
            renewable=True,
            explicit_max_ttl=self.client_token_max_ttl,
            metadata={
                "managed_by": "mlox",
                "service_uuid": self.uuid,
                "purpose": "mlox-secret-manager-client",
            },
        )

    def _store_client_token_auth(self, auth: Dict[str, Any]) -> None:
        token = auth.get("client_token")
        if token:
            self.client_token = str(token)
        accessor = auth.get("accessor")
        if accessor:
            self.client_token_accessor = str(accessor)
        if auth.get("lease_duration") is not None:
            self.client_token_lease_duration = int(auth.get("lease_duration") or 0)
        if auth.get("renewable") is not None:
            self.client_token_renewable = bool(auth.get("renewable"))
        self.client_token_last_renewed_at = datetime.now(timezone.utc).isoformat()

    def _bootstrap_openbao(self, conn) -> None:
        health = self._wait_for_container_health(conn)

        if not bool(health.get("initialized", False)):
            logger.info("Initializing OpenBao with %s key share(s).", self.key_shares)
            init_result = self._bao_json(
                conn,
                "operator",
                "init",
                f"-key-shares={self.key_shares}",
                f"-key-threshold={self.key_threshold}",
                "-format=json",
            )
            self.root_token = str(init_result.get("root_token", ""))
            keys = (
                init_result.get("unseal_keys_b64")
                or init_result.get("keys_base64")
                or init_result.get("keys")
                or []
            )
            self.unseal_keys = [str(key) for key in keys]
            if not self.unseal_keys:
                raise RuntimeError(
                    "OpenBao initialization did not return unseal keys. "
                    f"Response keys: {list(init_result.keys())}"
                )
            health = self._wait_for_container_health(conn)

        if bool(health.get("sealed", True)):
            logger.info("Unsealing OpenBao with stored unseal key material.")
            if not self.unseal_keys:
                raise RuntimeError(
                    "OpenBao is sealed and no unseal keys are available in mlox state."
                )
            for key in self.unseal_keys:
                health = self._bao_json(
                    conn,
                    "operator",
                    "unseal",
                    "-format=json",
                    key,
                    token=self.root_token,
                )
                if not bool(health.get("sealed", True)):
                    break

        if bool(health.get("sealed", True)):
            raise RuntimeError("OpenBao remained sealed after submitting unseal keys.")
        if not self.root_token:
            raise RuntimeError("OpenBao is initialized but no root token is available.")


    def _wait_for_container_health(self, conn) -> Dict:
        last_error: Exception | None = None
        for attempt in range(1, 31):
            try:
                health = self._bao_json(conn, "status", "-format=json", allow_failure=True)
                if not isinstance(health.get("initialized"), bool) or not isinstance(
                    health.get("sealed"), bool
                ):
                    raise RuntimeError(f"OpenBao status is not ready: {health}")
                logger.info(
                    "OpenBao health attempt %s: initialized=%s sealed=%s.",
                    attempt,
                    health.get("initialized"),
                    health.get("sealed"),
                )
                return health
            except Exception as exc:  # pragma: no cover - network timing path
                last_error = exc
                logger.info("Waiting for OpenBao health check: %s", exc)
                time.sleep(2)
        logs = self._container_logs(conn, tail=120)
        raise RuntimeError(
            "OpenBao did not become reachable. "
            f"Last health error: {last_error}. Recent container logs:\n{logs}"
        )

    def _compose_up_with_timeout(self, conn, timeout_seconds: int = 300) -> bool:
        compose_file = f"{self.target_path}/{self.target_docker_script}"
        env_file = f"{self.target_path}/{self.target_docker_env}"
        command = (
            f"timeout {timeout_seconds}s docker compose --env-file {env_file} "
            f'-f "{compose_file}" up -d --build --force-recreate'
        )
        result = self.exec.execute(
            conn,
            command,
            group=TaskGroup.CONTAINER_RUNTIME,
            sudo=True,
            description="Start OpenBao docker compose stack",
        )
        if result is None:
            raise RuntimeError(
                "OpenBao docker compose startup failed or timed out after "
                f"{timeout_seconds} seconds."
            )
        self.state = "running"
        return True

    def _bao_json(
        self,
        conn,
        *args: str,
        token: str | None = None,
        allow_failure: bool = False,
    ) -> Dict:
        output = self._bao(conn, *args, token=token, allow_failure=allow_failure)
        try:
            return json.loads(output or "{}")
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"OpenBao returned non-JSON output: {output}") from exc

    def _bao(
        self,
        conn,
        *args: str,
        token: str | None = None,
        allow_failure: bool = False,
    ) -> str:
        env = ["-e", "BAO_ADDR=https://127.0.0.1:8200", "-e", "BAO_SKIP_VERIFY=true"]
        if token:
            env.extend(["-e", f"BAO_TOKEN={token}"])
        command = " ".join(
            [
                "docker",
                "exec",
                *[shlex.quote(part) for part in env],
                shlex.quote(self.compose_service_names["OpenBao"]),
                "bao",
                *[shlex.quote(arg) for arg in args],
            ]
        )
        if allow_failure:
            command = f"{command} || true"
        result = self.exec.execute(
            conn,
            command,
            group=TaskGroup.CONTAINER_RUNTIME,
            sudo=True,
            description="Run OpenBao CLI command in container",
        )
        if result is None:
            raise RuntimeError(f"OpenBao CLI command failed: bao {' '.join(args)}")
        return result

    def _container_logs(self, conn, *, tail: int = 80) -> str:
        container = self.compose_service_names.get("OpenBao", "")
        if not container:
            return "OpenBao container name is not known."
        result = self.exec.execute(
            conn,
            f"docker logs --tail {int(tail)} {shlex.quote(container)}",
            group=TaskGroup.CONTAINER_RUNTIME,
            sudo=True,
            description="Read OpenBao container logs",
        )
        return result or ""
