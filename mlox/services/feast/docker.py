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
class FeastDockerService(AbstractService):
    config: str
    dockerfile: str
    # user: str
    # pw: str
    registry_port: str | int
    online_port: str | int
    offline_port: str | int
    service_url: str = field(init=False, default="")
    compose_service_names: Dict[str, str] = field(
        init=False,
        default_factory=lambda: {
            "Feast Redis": "feast-redis",
            "Feast Init": "feast-init",
            "Feast Registry": "feast-registry",
            "Feast Offline": "feast-offline",
            "Feast Online": "feast-online",
        },
    )

    def setup(self, conn) -> None:
        self.exec.fs_create_dir(conn, self.target_path)
        self.exec.fs_copy(conn, self.template, f"{self.target_path}/{self.target_docker_script}")
        self.exec.fs_copy(conn, self.config, f"{self.target_path}/feature_store.yaml")
        self.exec.fs_copy(conn, self.dockerfile, f"{self.target_path}/Dockerfile")
        self.exec.tls_setup(conn, conn.host, self.target_path)
        self.certificate = self.exec.fs_read_file(
            conn, f"{self.target_path}/cert.pem", format="txt/plain"
        )

        env_path = f"{self.target_path}/{self.target_docker_env}"
        self.exec.fs_create_empty_file(conn, env_path)
        self.exec.fs_append_line(conn, env_path, f"FEAST_REGISTRY_PORT={self.registry_port}")
        self.exec.fs_append_line(conn, env_path, f"FEAST_ONLINE_PORT={self.online_port}")
        self.exec.fs_append_line(conn, env_path, f"FEAST_OFFLINE_PORT={self.offline_port}")
        self.exec.fs_append_line(conn, env_path, f"FEAST_PROJECT_NAME=my_project")
        # self.exec.fs_append_line(conn, env_path, f"MY_FEAST_USER={self.user}")
        # self.exec.fs_append_line(conn, env_path, f"MY_FEAST_PW={self.pw}")

        self.service_ports["registry"] = int(self.registry_port)
        self.service_ports["online_store"] = int(self.online_port)
        self.service_ports["offline_store"] = int(self.offline_port)
        self.service_urls["Feast"] = f"https://{conn.host}:{self.registry_port}"
        self.service_url = (
            f"tcp://{conn.host}:{self.registry_port}"  # Default Feast port
        )

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
        return {"status": "unknown"}

    def get_secrets(self) -> Dict[str, Dict]:
        return {}
