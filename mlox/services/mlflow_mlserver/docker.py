import logging

from typing import Dict
from passlib.hash import apr_md5_crypt  # type: ignore
from dataclasses import dataclass, field

from mlox.service import AbstractService, DockerMixin
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
    level=logging.INFO,
    format="[%(levelname)s] %(asctime)s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)


@dataclass
class MLFlowMLServerDockerService(DockerMixin, AbstractService):
    dockerfile: str
    port: str | int
    model: str
    tracking_uri: str
    tracking_user: str
    tracking_pw: str
    user: str = "admin"
    pw: str = "s3cr3t"
    hashed_pw: str = field(default="", init=False)
    service_url: str = field(init=False, default="")
    compose_service_names: Dict[str, str] = field(init=False, default_factory=dict)

    def __post_init__(self):
        if not self.name.startswith(f"{self.model}@"):
            self.name = f"{self.model}@{self.name}"
        if not self.target_path.endswith(f"-{self.port}"):
            self.target_path = f"{self.target_path}-{self.port}"
        self.compose_service_names = {
            "Traefik": f"traefik_reverse_proxy_mlserver_{self.port}",
            "MLServer": f"mlflow_mlserver_{self.port}",
        }

    def _generate_htpasswd_entry(self) -> None:
        """Generates an APR1-MD5 htpasswd entry, escaped for Traefik."""
        # Generate APR1-MD5 hash
        apr1_hash = apr_md5_crypt.hash(self.pw)
        # Escape '$' for Traefik: "$apr1$..." becomes "$$apr1$$..."
        self.hashed_pw = apr1_hash.replace("$", "$$")

    def setup(self, conn) -> None:
        fs_create_dir(conn, self.target_path)
        fs_copy(conn, self.template, f"{self.target_path}/{self.target_docker_script}")
        fs_copy(conn, self.dockerfile, f"{self.target_path}/dockerfile-mlflow-mlserver")
        # fs_copy(conn, self.settings, f"{self.target_path}/settings.json")
        # tls_setup(conn, conn.host, self.target_path)

        # Generate with: echo $(htpasswd -nb your_user your_password) | sed -e s/\\$/\\$\\$/g
        # Format: admin:$$apr1$$vEr/wAAE$$xaB99Pf.qkH3QFrgITm0P/
        self._generate_htpasswd_entry()

        env_path = f"{self.target_path}/{self.target_docker_env}"
        fs_create_empty_file(conn, env_path)
        fs_append_line(
            conn, env_path, f"TRAEFIK_USER_AND_PW={self.user}:{self.hashed_pw}"
        )
        fs_append_line(conn, env_path, f"MLSERVER_ENDPOINT_URL={conn.host}")
        fs_append_line(conn, env_path, f"MLSERVER_ENDPOINT_PORT={self.port}")
        fs_append_line(conn, env_path, f"MLFLOW_REMOTE_MODEL={self.model}")
        fs_append_line(conn, env_path, f"MLFLOW_REMOTE_URI={self.tracking_uri}")
        fs_append_line(conn, env_path, f"MLFLOW_REMOTE_USER={self.tracking_user}")
        fs_append_line(conn, env_path, f"MLFLOW_REMOTE_PW={self.tracking_pw}")
        fs_append_line(conn, env_path, f"MLFLOW_REMOTE_INSECURE=true")
        self.service_ports["MLServer REST API"] = int(self.port)
        self.service_urls["MLServer REST API"] = f"https://{conn.host}:{self.port}"
        self.service_url = f"https://{conn.host}:{self.port}"

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
        return {}
