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
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)


@dataclass
class InfluxDockerService(AbstractService):
    user: str
    pw: str
    port: str | int
    token: str

    def setup(self, conn) -> None:
        fs_create_dir(conn, self.target_path)

        fs_copy(conn, self.template, f"{self.target_path}/{self.target_docker_script}")
        tls_setup(conn, conn.host, self.target_path)
        self.certificate = fs_read_file(
            conn, f"{self.target_path}/cert.pem", format="txt/plain"
        )

        env_path = f"{self.target_path}/{self.target_docker_env}"
        fs_append_line(conn, env_path, f"INFLUXDB_PORT={self.port}")

        env_admin_path = f"{self.target_path}/.env.influxdb2-admin-username"
        env_pw_path = f"{self.target_path}/.env.influxdb2-admin-password"
        env_token_path = f"{self.target_path}/.env.influxdb2-admin-token"

        fs_append_line(conn, env_admin_path, self.user)
        fs_append_line(conn, env_pw_path, self.pw)
        fs_append_line(conn, env_token_path, self.token)

        exec_command(
            conn,
            f"cat {self.target_path}/cert.pem {self.target_path}/key.pem > {self.target_path}/influxdb.pem",
        )

        self.service_ports["InfluxDB"] = int(self.port)
        self.service_urls["InfluxDB"] = f"https://{conn.host}:{self.port}"

    def teardown(self, conn):
        docker_down(
            conn,
            f"{self.target_path}/{self.target_docker_script}",
            remove_volumes=True,
        )
        fs_delete_dir(conn, self.target_path)

    def check(self, conn) -> Dict:
        return {"status": "unknown"}
