import logging

from dataclasses import dataclass, field
from typing import Dict

from mlox.service import AbstractService, tls_setup_no_config
from mlox.remote import (
    fs_copy,
    fs_create_dir,
    fs_create_empty_file,
    fs_append_line,
    docker_down,
    fs_delete_dir,
)


# Configure logging (optional, but recommended)
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)


@dataclass
class MLFlowMLServerDockerService(AbstractService):
    dockerfile: str
    port: str | int
    model: str
    tracking_uri: str
    tracking_user: str
    tracking_pw: str

    def setup(self, conn) -> None:
        fs_create_dir(conn, self.target_path)
        fs_copy(conn, self.template, f"{self.target_path}/{self.target_docker_script}")
        fs_copy(conn, self.dockerfile, f"{self.target_path}/dockerfile-mlflow-mlserver")
        env_path = f"{self.target_path}/{self.target_docker_env}"
        fs_create_empty_file(conn, env_path)
        fs_append_line(conn, env_path, f"MLSERVER_ENDPOINT_PORT={self.port}")
        fs_append_line(conn, env_path, f"MLFLOW_REMOTE_MODEL={self.model}")
        fs_append_line(conn, env_path, f"MLFLOW_REMOTE_URI={self.tracking_uri}")
        fs_append_line(conn, env_path, f"MLFLOW_REMOTE_USER={self.tracking_user}")
        fs_append_line(conn, env_path, f"MLFLOW_REMOTE_PW={self.tracking_pw}")
        fs_append_line(conn, env_path, f"MLFLOW_REMOTE_INSECURE=true")
        self.service_ports["MLServer REST API"] = int(self.port)
        self.service_url = f"https://{conn.host}:{self.port}/"

    def teardown(self, conn):
        docker_down(
            conn,
            f"{self.target_path}/{self.target_docker_script}",
            remove_volumes=True,
        )
        fs_delete_dir(conn, self.target_path)

    def check(self, conn) -> Dict:
        return {}
