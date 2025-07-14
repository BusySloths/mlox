import logging
import hashlib
import base64

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
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
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

    def setup(self, conn) -> None:
        fs_create_dir(conn, self.target_path)
        fs_copy(conn, self.template, f"{self.target_path}/{self.target_docker_script}")
        fs_copy(conn, self.config, f"{self.target_path}/milvus.conf")
        tls_setup(conn, conn.host, self.target_path)
        self.certificate = fs_read_file(
            conn, f"{self.target_path}/cert.pem", format="txt/plain"
        )

        # Create htpasswd file for basic auth without depending on htpasswd command
        htpasswd_path = f"{self.target_path}/htpasswd"
        htpasswd_entry = _generate_htpasswd_sha1(self.user, self.pw)
        fs_create_empty_file(conn, htpasswd_path)
        fs_append_line(conn, htpasswd_path, htpasswd_entry)

        env_path = f"{self.target_path}/{self.target_docker_env}"
        fs_create_empty_file(conn, env_path)

        self.service_ports["Milvus"] = int(self.port)
        self.service_urls["Milvus"] = f"https://{conn.host}:{self.port}"
        self.service_url = f"http://{conn.host}:19530"  # Default Milvus port

    def teardown(self, conn):
        docker_down(
            conn,
            f"{self.target_path}/{self.target_docker_script}",
            remove_volumes=True,
        )
        fs_delete_dir(conn, self.target_path)

    def check(self, conn) -> Dict:
        return {"status": "unknown"}
