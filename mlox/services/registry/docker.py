"""Docker-based private registry service implementation."""

from __future__ import annotations

import crypt
import logging

from dataclasses import dataclass, field
from typing import Dict

from mlox.service import AbstractService


logger = logging.getLogger(__name__)


@dataclass
class RegistryDockerService(AbstractService):
    """Manage a TLS and basic-auth protected Docker distribution registry."""

    username: str
    password: str
    port: str | int
    realm: str = "Registry Realm"
    compose_service_names: Dict[str, str] = field(
        init=False, default_factory=lambda: {"Registry": "registry"}
    )

    def setup(self, conn) -> None:
        self.exec.fs_create_dir(conn, self.target_path)

        self.exec.fs_copy(
            conn, self.template, f"{self.target_path}/{self.target_docker_script}"
        )

        self.exec.tls_setup(conn, conn.host, self.target_path)
        self.certificate = self.exec.fs_read_file(
            conn, f"{self.target_path}/cert.pem", format="txt/plain"
        )

        certs_dir = f"{self.target_path}/certs"
        auth_dir = f"{self.target_path}/auth"
        data_dir = f"{self.target_path}/data"
        self.exec.fs_create_dir(conn, certs_dir)
        self.exec.fs_create_dir(conn, auth_dir)
        self.exec.fs_create_dir(conn, data_dir)

        self.exec.fs_copy_remote_file(
            conn, f"{self.target_path}/cert.pem", f"{certs_dir}/domain.crt"
        )
        self.exec.fs_copy_remote_file(
            conn, f"{self.target_path}/key.pem", f"{certs_dir}/domain.key"
        )

        htpasswd_entry = self._generate_htpasswd_entry(self.username, self.password)
        self.exec.fs_write_file(conn, f"{auth_dir}/htpasswd", htpasswd_entry)

        env_path = f"{self.target_path}/{self.target_docker_env}"
        self.exec.fs_append_line(conn, env_path, f"REGISTRY_PORT={self.port}")
        self.exec.fs_append_line(
            conn, env_path, "REGISTRY_HTTP_TLS_CERTIFICATE=/certs/domain.crt"
        )
        self.exec.fs_append_line(
            conn, env_path, "REGISTRY_HTTP_TLS_KEY=/certs/domain.key"
        )
        self.exec.fs_append_line(conn, env_path, "REGISTRY_AUTH=htpasswd")
        self.exec.fs_append_line(
            conn, env_path, "REGISTRY_AUTH_HTPASSWD_PATH=/auth/htpasswd"
        )
        self.exec.fs_append_line(
            conn, env_path, f"REGISTRY_AUTH_HTPASSWD_REALM={self.realm}"
        )
        self.exec.fs_append_line(
            conn, env_path, "REGISTRY_STORAGE_DELETE_ENABLED=true"
        )

        try:
            port_int = int(self.port)
        except (TypeError, ValueError):
            port_int = 5000
        self.service_ports["Registry"] = port_int
        self.service_urls["Registry"] = f"https://{conn.host}:{port_int}"

    def teardown(self, conn):
        self.exec.docker_down(
            conn,
            f"{self.target_path}/{self.target_docker_script}",
            remove_volumes=True,
        )
        self.exec.fs_delete_dir(conn, self.target_path)

    def spin_up(self, conn) -> bool:
        return self.compose_up(conn)

    def spin_down(self, conn) -> bool:
        return self.compose_down(conn)

    def check(self, conn) -> Dict:
        try:
            state = self.exec.docker_service_state(
                conn, self.compose_service_names["Registry"]
            )
            if state and state.strip() == "running":
                self.state = "running"
                return {"status": "running"}
            self.state = "stopped"
            return {"status": "stopped"}
        except Exception as exc:  # pragma: no cover - defensive logging path
            logger.error("Error checking registry service status: %s", exc)
            self.state = "unknown"
        return {"status": "unknown"}

    def get_secrets(self) -> Dict[str, Dict]:
        if not self.username and not self.password:
            return {}

        secret: Dict[str, str] = {}
        if self.username:
            secret["username"] = self.username
        if self.password:
            secret["password"] = self.password
        registry_url = self.service_urls.get("Registry")
        if registry_url:
            secret["registry_url"] = registry_url
        if self.certificate:
            secret["certificate"] = self.certificate

        return {"registry_credentials": secret}

    @staticmethod
    def _generate_htpasswd_entry(username: str, password: str) -> str:
        if not username:
            raise ValueError("username must be provided for registry auth")
        if not password:
            raise ValueError("password must be provided for registry auth")

        method = getattr(crypt, "METHOD_SHA512", None)
        if method is not None:
            salt = crypt.mksalt(method)
            hashed = crypt.crypt(password, salt)
        else:  # pragma: no cover - fallback for limited platforms
            hashed = crypt.crypt(password)
        if not hashed:
            raise ValueError("failed to generate htpasswd hash")
        return f"{username}:{hashed}\n"
