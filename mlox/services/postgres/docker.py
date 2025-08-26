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

    def check(self, conn) -> Dict:
        return {"status": "unknown"}
