"""Docker deployment adapter for Milvus vector database services.

Purpose:
- Prepare Milvus Compose runtime files, environment variables, and reachable service URLs.

Key public classes/functions:
- ``MilvusDockerService``

Expected runtime mode:
- Remote executor (invoked from CLI/UI/TUI orchestration)

Related modules (plain-text links):
- mlox.service
- mlox.services.milvus.ui
"""

import logging
import hashlib
import base64

from dataclasses import dataclass, field
from typing import Dict

from mlox.service import AbstractService


# Configure logging (optional, but recommended)
logging.basicConfig(
    level=logging.INFO,
    format="[%(levelname)s] %(asctime)s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)


def _generate_htpasswd_sha1(user: str, password: str) -> str:
    """Generates a htpasswd entry using SHA1, supported by many web servers."""
    sha1_hash = hashlib.sha1(password.encode("utf-8")).digest()
    b64_hash = base64.b64encode(sha1_hash).decode("utf-8")
    return f"{user}:{{SHA}}{b64_hash}"


@dataclass
class MilvusDockerService(AbstractService):
    config: str
    user: str
    pw: str
    port: str | int
    service_url: str = field(init=False, default="")
    compose_service_names: Dict[str, str] = field(
        init=False,
        default_factory=lambda: {
            "Milvus": "milvus",
            "Milvus MinIO": "milvus-minio",
            "Milvus Etcd": "milvus-etcd",
        },
    )

    def setup(self, conn) -> None:
        self.exec.fs_create_dir(conn, self.target_path)
        self.exec.fs_copy(
            conn, self.template, f"{self.target_path}/{self.target_docker_script}"
        )
        self.exec.fs_copy(conn, self.config, f"{self.target_path}/milvus.yaml")
        self.exec.tls_setup(conn, conn.host, self.target_path)
        self.certificate = self.exec.fs_read_file(
            conn, f"{self.target_path}/cert.pem", format="txt/plain"
        )

        env_path = f"{self.target_path}/{self.target_docker_env}"
        self.exec.fs_create_empty_file(conn, env_path)
        self.exec.fs_append_line(conn, env_path, f"MY_MILVUS_PORT={self.port}")
        self.exec.fs_append_line(conn, env_path, f"MY_MILVUS_USER={self.user}")
        self.exec.fs_append_line(conn, env_path, f"MY_MILVUS_PW={self.pw}")

        self.service_ports["Milvus"] = int(self.port)
        self.service_urls["Milvus"] = f"https://{conn.host}:{self.port}"
        self.service_url = f"tcp://{conn.host}:{self.port}"  # Default Milvus port

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
        return {"milvus_credentials": credentials}
