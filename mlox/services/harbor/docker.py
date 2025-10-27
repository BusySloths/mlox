from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict

from mlox.service import AbstractService


@dataclass
class HarborDockerService(AbstractService):
    """Manage a self-hosted Harbor registry via Docker Compose."""

    hostname: str
    https_port: str | int
    registry_port: str | int
    admin_username: str
    admin_password: str
    database_password: str
    redis_password: str
    core_secret: str
    jobservice_secret: str
    registry_http_secret: str

    service_url: str = field(init=False, default="")
    registry_url: str = field(init=False, default="")
    compose_service_names: Dict[str, str] = field(
        init=False,
        default_factory=lambda: {
            "Harbor Nginx": "harbor-nginx",
            "Harbor Core": "harbor-core",
            "Harbor Jobservice": "harbor-jobservice",
            "Harbor Portal": "harbor-portal",
            "Harbor Registry": "harbor-registry",
            "Harbor Database": "harbor-db",
        },
    )

    def __post_init__(self) -> None:
        self.https_port = int(self.https_port)
        self.registry_port = int(self.registry_port)
        self.service_ports["Harbor HTTPS"] = self.https_port
        self.service_ports["Harbor Registry"] = self.registry_port
        self.service_url = f"https://{self.hostname}:{self.https_port}"
        self.registry_url = f"https://{self.hostname}:{self.registry_port}"
        self.service_urls["Harbor UI"] = self.service_url
        self.service_urls["Harbor Registry"] = self.registry_url

    # ---- lifecycle -----------------------------------------------------
    def setup(self, conn) -> None:
        self.exec.fs_create_dir(conn, self.target_path)
        self.exec.fs_copy(
            conn, self.template, f"{self.target_path}/{self.target_docker_script}"
        )

        tls_host = self.hostname or getattr(conn, "host", "localhost")
        self.hostname = tls_host
        self.service_url = f"https://{tls_host}:{self.https_port}"
        self.registry_url = f"https://{tls_host}:{self.registry_port}"
        self.service_urls["Harbor UI"] = self.service_url
        self.service_urls["Harbor Registry"] = self.registry_url
        self.exec.fs_create_dir(conn, f"{self.target_path}/data/log")
        self.exec.tls_setup(conn, tls_host, self.target_path)
        self.certificate = self.exec.fs_read_file(
            conn, f"{self.target_path}/cert.pem", format="txt/plain"
        )

        env_path = f"{self.target_path}/{self.target_docker_env}"
        self.exec.fs_create_empty_file(conn, env_path)
        for key, value in self._environment_variables(conn).items():
            self.exec.fs_append_line(conn, env_path, f"{key}={value}")

        self.exec.fs_write_file(
            conn,
            f"{self.target_path}/harbor.yml",
            self._render_harbor_configuration(),
        )

    def teardown(self, conn) -> None:
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

    # ---- health -------------------------------------------------------
    def check(self, conn) -> Dict:
        try:
            statuses = self.compose_service_status(conn)
        except Exception:
            self.state = "unknown"
            return {"status": "unknown"}

        if not statuses:
            self.state = "stopped"
            return {"status": "stopped"}

        if all(state and "running" in state.lower() for state in statuses.values()):
            self.state = "running"
            return {"status": "running", "services": statuses}

        if any(state and "running" in state.lower() for state in statuses.values()):
            self.state = "running"
            return {"status": "running", "services": statuses}

        self.state = "unknown"
        return {"status": "unknown", "services": statuses}

    # ---- secrets ------------------------------------------------------
    def get_secrets(self) -> Dict[str, Dict]:
        secrets: Dict[str, Dict] = {}
        if self.admin_username and self.admin_password:
            secrets["harbor_admin_credentials"] = {
                "username": self.admin_username,
                "password": self.admin_password,
            }
        secrets["harbor_registry"] = {
            "hostname": self.hostname,
            "registry_url": self.registry_url,
            "certificate": self.certificate or "",
        }
        return secrets

    # ---- helpers ------------------------------------------------------
    def _environment_variables(self, conn) -> Dict[str, str]:
        host = self.hostname or getattr(conn, "host", "localhost")
        return {
            "HARBOR_HOSTNAME": host,
            "HARBOR_HTTPS_PORT": str(self.https_port),
            "HARBOR_REGISTRY_PORT": str(self.registry_port),
            "HARBOR_ADMIN_USERNAME": self.admin_username,
            "HARBOR_ADMIN_PASSWORD": self.admin_password,
            "HARBOR_DATABASE_PASSWORD": self.database_password,
            "HARBOR_REDIS_PASSWORD": self.redis_password,
            "HARBOR_CORE_SECRET": self.core_secret,
            "HARBOR_JOBSERVICE_SECRET": self.jobservice_secret,
            "HARBOR_REGISTRY_HTTP_SECRET": self.registry_http_secret,
            "HARBOR_TLS_CERT_PATH": "./cert.pem",
            "HARBOR_TLS_KEY_PATH": "./key.pem",
            "HARBOR_CONFIG_PATH": "./harbor.yml",
        }

    def _render_harbor_configuration(self) -> str:
        return (
            "\n".join(
                [
                    f"hostname: {self.hostname}",
                    "http:",
                    "  port: 80",
                    "https:",
                    f"  port: {self.https_port}",
                    "  certificate: /etc/harbor/tls/harbor.crt",
                    "  private_key: /etc/harbor/tls/harbor.key",
                    f"harbor_admin_password: {self.admin_password}",
                    "data_volume: /data",
                    "database:",
                    f"  password: {self.database_password}",
                    "  max_idle_conns: 100",
                    "  max_open_conns: 900",
                    "redis:",
                    f"  password: {self.redis_password}",
                    "jobservice:",
                    "  max_job_workers: 10",
                    "log:",
                    "  level: info",
                    "notification:",
                    "  webhook_job_max_retry: 3",
                    "chart:",
                    "  absolute_url: disabled",
                    "trivy:",
                    "  ignore_unfixed: false",
                    "  offline_scan: false",
                    "  skip_update: false",
                ]
            )
            + "\n"
        )
