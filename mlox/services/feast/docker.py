import logging

from dataclasses import dataclass, field
from typing import Dict

from mlox.service import AbstractService, tls_setup
from mlox.remote import (
    fs_copy,
    fs_read_file,
    fs_create_dir,
    fs_append_line,
    fs_create_empty_file,
    docker_down,
    fs_delete_dir,
)


# Configure logging (optional, but recommended)
logging.basicConfig(
    level=logging.INFO,
    format="[%(levelname)s] %(asctime)s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)


@dataclass
class FeastDockerService(AbstractService):
    config: str
    dockerfile: str
    # user: str
    # pw: str
    registry_port: str | int
    online_port: str | int
    offline_port: str | int
    service_url: str = field(init=False, default="")

    def setup(self, conn) -> None:
        fs_create_dir(conn, self.target_path)
        fs_copy(conn, self.template, f"{self.target_path}/{self.target_docker_script}")
        fs_copy(conn, self.config, f"{self.target_path}/feature_store.yaml")
        fs_copy(conn, self.dockerfile, f"{self.target_path}/Dockerfile")
        tls_setup(conn, conn.host, self.target_path)
        self.certificate = fs_read_file(
            conn, f"{self.target_path}/cert.pem", format="txt/plain"
        )

        env_path = f"{self.target_path}/{self.target_docker_env}"
        fs_create_empty_file(conn, env_path)
        fs_append_line(conn, env_path, f"FEAST_REGISTRY_PORT={self.registry_port}")
        fs_append_line(conn, env_path, f"FEAST_ONLINE_PORT={self.online_port}")
        fs_append_line(conn, env_path, f"FEAST_OFFLINE_PORT={self.offline_port}")
        fs_append_line(conn, env_path, f"FEAST_PROJECT_NAME=my_project")
        # fs_append_line(conn, env_path, f"MY_FEAST_USER={self.user}")
        # fs_append_line(conn, env_path, f"MY_FEAST_PW={self.pw}")

        self.service_ports["registry"] = int(self.registry_port)
        self.service_ports["online_store"] = int(self.online_port)
        self.service_ports["offline_store"] = int(self.offline_port)
        self.service_urls["Feast"] = f"https://{conn.host}:{self.registry_port}"
        self.service_url = (
            f"tcp://{conn.host}:{self.registry_port}"  # Default Feast port
        )

    def teardown(self, conn):
        docker_down(
            conn,
            f"{self.target_path}/{self.target_docker_script}",
            remove_volumes=True,
        )
        fs_delete_dir(conn, self.target_path)

    def check(self, conn) -> Dict:
        return {"status": "unknown"}
