"""Docker deployment adapter for PostgreSQL database services.

Purpose:
- Provision PostgreSQL containers, set credentials/database vars, and register connection URLs.

Key public classes/functions:
- ``PostgresDockerService``

Expected runtime mode:
- Remote executor (invoked from CLI/UI/TUI orchestration)

Related modules (plain-text links):
- mlox.service
- mlox.services.postgres.ui
"""

import logging

from dataclasses import dataclass, field
from typing import Dict

from mlox.service import AbstractService


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
        self.exec.fs_create_dir(conn, self.target_path)

        self.exec.fs_copy(
            conn, self.template, f"{self.target_path}/{self.target_docker_script}"
        )
        self.exec.tls_setup(conn, conn.host, self.target_path)
        self.certificate = self.exec.fs_read_file(
            conn, f"{self.target_path}/cert.pem", format="txt/plain"
        )

        env_path = f"{self.target_path}/{self.target_docker_env}"
        self.exec.fs_append_line(conn, env_path, f"MY_POSTGRES_PORT={self.port}")
        self.exec.fs_append_line(conn, env_path, f"MY_POSTGRES_USER={self.user}")
        self.exec.fs_append_line(conn, env_path, f"MY_POSTGRES_PW={self.pw}")
        self.exec.fs_append_line(conn, env_path, f"MY_POSTGRES_DB={self.db}")

        self.service_ports["Postgres"] = int(self.port)
        self.service_urls["Postgres"] = f"https://{conn.host}:{self.port}"
        self.service_urls["Postgres IP"] = f"{conn.host}"

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
                conn, self.compose_service_names["Postgres"]
            )
            if state.strip() == "running":
                self.state = "running"
                return {"status": "running"}
            else:
                self.state = "stopped"
                return {"status": "stopped"}
        except Exception as e:
            logging.error(f"Error checking Postgres service status: {e}")
            self.state = "unknown"
        return {"status": "unknown"}

    def get_secrets(self) -> Dict[str, Dict]:
        port_val = self.service_ports.get("Postgres") or int(self.port)
        host_val = self.service_urls.get("Postgres IP", "")
        connection = {
            "host": host_val,
            "port": str(port_val),
            "database": self.db,
            "username": self.user,
            "password": self.pw,
            "certificate": self.certificate,
        }
        if host_val and self.db:
            connection["dsn"] = (
                f"postgresql://{self.user}:{self.pw}@{host_val}:{port_val}/{self.db}"
                if self.user and self.pw
                else f"postgresql://{host_val}:{port_val}/{self.db}"
            )
        return {"postgres_connection": connection}
