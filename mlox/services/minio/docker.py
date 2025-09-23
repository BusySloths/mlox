import logging

from dataclasses import dataclass, field
from typing import Dict

from mlox.service import AbstractService, tls_setup
from mlox.remote import (
    docker_down,
    fs_append_line,
    fs_copy,
    fs_create_dir,
    fs_delete_dir,
    fs_read_file,
)
from mlox.remote import docker_all_service_states


logging.basicConfig(
    level=logging.INFO,
    format="[%(levelname)s] %(asctime)s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)


@dataclass
class MinioDockerService(AbstractService):
    root_user: str
    root_password: str
    api_port: str | int
    console_port: str | int
    service_url: str = field(init=False, default="")
    console_url: str = field(init=False, default="")
    compose_service_names: Dict[str, str] = field(
        init=False,
        default_factory=lambda: {"MinIO": "minio"},
    )

    def setup(self, conn) -> None:
        fs_create_dir(conn, self.target_path)
        fs_copy(conn, self.template, f"{self.target_path}/{self.target_docker_script}")

        tls_setup(conn, conn.host, self.target_path)
        self.certificate = fs_read_file(
            conn, f"{self.target_path}/cert.pem", format="txt/plain"
        )

        env_path = f"{self.target_path}/{self.target_docker_env}"
        fs_append_line(conn, env_path, f"MINIO_ROOT_USER={self.root_user}")
        fs_append_line(conn, env_path, f"MINIO_ROOT_PASSWORD={self.root_password}")
        fs_append_line(conn, env_path, f"MINIO_PUBLIC_URL={conn.host}")
        fs_append_line(conn, env_path, f"MINIO_API_PORT={self.api_port}")
        fs_append_line(conn, env_path, f"MINIO_CONSOLE_PORT={self.console_port}")

        self.service_ports["MinIO API"] = int(self.api_port)
        self.service_ports["MinIO Console"] = int(self.console_port)
        self.service_url = f"https://{conn.host}:{self.api_port}"
        self.console_url = f"https://{conn.host}:{self.console_port}"
        self.service_urls["MinIO API"] = self.service_url
        self.service_urls["MinIO Console"] = self.console_url

    def teardown(self, conn):
        docker_down(
            conn,
            f"{self.target_path}/{self.target_docker_script}",
            remove_volumes=True,
        )
        fs_delete_dir(conn, self.target_path)

    def spin_up(self, conn) -> bool:
        return self.compose_up(conn)

    def spin_down(self, conn) -> bool:
        return self.compose_down(conn)

    def check(self, conn) -> Dict:
        try:
            states = docker_all_service_states(conn)
            if not states:
                # no containers found
                self.state = "stopped"
                return {"status": "stopped"}

            # look for any container name that contains 'minio' and is running
            for name, state in states.items():
                try:
                    if "minio" in name and state.get("Status") == "running":
                        self.state = "running"
                        return {"status": "running"}
                except Exception:
                    # ignore malformed state entries
                    continue

            # no matching running container found
            self.state = "stopped"
            return {"status": "stopped"}
        except Exception as exc:  # pragma: no cover - defensive logging path
            logging.error("Error checking MinIO service status: %s", exc)
            self.state = "unknown"
        return {"status": "unknown"}
