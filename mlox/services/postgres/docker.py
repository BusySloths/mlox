import logging

from dataclasses import dataclass, field
from typing import Dict

from mlox.service import AbstractService, tls_setup
from mlox.remote import (
    fs_copy,
    fs_read_file,
    fs_create_dir,
    fs_append_line,
    docker_down,
    fs_delete_dir,
    exec_command,
)


# Configure logging (optional, but recommended)
logging.basicConfig(
    level=logging.INFO,
    format="[%(levelname)s] %(asctime)s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)


@dataclass
class PostgresDockerService(AbstractService):
    user: str
    pw: str
    db: str
    port: str | int
    compose_service_names: Dict[str, str] = field(
        init=False,
        default_factory=lambda: {"Postgres": "postgres"},
    )

    def setup(self, conn) -> None:
        fs_create_dir(conn, self.target_path)

        fs_copy(conn, self.template, f"{self.target_path}/{self.target_docker_script}")
        tls_setup(conn, conn.host, self.target_path)
        self.certificate = fs_read_file(
            conn, f"{self.target_path}/cert.pem", format="txt/plain"
        )

        env_path = f"{self.target_path}/{self.target_docker_env}"
        fs_append_line(conn, env_path, f"MY_POSTGRES_PORT={self.port}")
        fs_append_line(conn, env_path, f"MY_POSTGRES_USER={self.user}")
        fs_append_line(conn, env_path, f"MY_POSTGRES_PW={self.pw}")
        fs_append_line(conn, env_path, f"MY_POSTGRES_DB={self.db}")

        self.service_ports["Postgres"] = int(self.port)
        self.service_urls["Postgres"] = f"https://{conn.host}:{self.port}"

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
            output = exec_command(
                conn,
                f"docker ps --filter 'name=postgres' --filter 'status=running' --format '{{{{.Names}}}}'",
                sudo=True,
            )
            if "postgres" in output:
                self.state = "running"
                return {"status": "running"}
            else:
                self.state = "stopped"
                return {"status": "stopped"}
        except Exception as e:
            logging.error(f"Error checking Redis service status: {e}")
            self.state = "unknown"
        return {"status": "unknown"}

    def get_secrets(self) -> Dict[str, Dict]:
        credentials = {
            key: value
            for key, value in {
                "username": self.user,
                "password": self.pw,
            }.items()
            if value
        }
        if not credentials:
            return {}
        return {"postgres_admin_credentials": credentials}
