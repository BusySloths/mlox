import logging

from typing import Dict
from passlib.hash import apr_md5_crypt  # type: ignore
from dataclasses import dataclass, field

from mlox.service import AbstractService



# Configure logging (optional, but recommended)
logging.basicConfig(
    level=logging.INFO,
    format="[%(levelname)s] %(asctime)s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)


@dataclass
class MLFlowMLServerDockerService(AbstractService):
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
        self.exec.fs_create_dir(conn, self.target_path)
        self.exec.fs_copy(conn, self.template, f"{self.target_path}/{self.target_docker_script}")
        self.exec.fs_copy(conn, self.dockerfile, f"{self.target_path}/dockerfile-mlflow-mlserver")
        # self.exec.fs_copy(conn, self.settings, f"{self.target_path}/settings.json")
        # self.exec.tls_setup(conn, conn.host, self.target_path)

        # Generate with: echo $(htpasswd -nb your_user your_password) | sed -e s/\\$/\\$\\$/g
        # Format: admin:$$apr1$$vEr/wAAE$$xaB99Pf.qkH3QFrgITm0P/
        self._generate_htpasswd_entry()

        env_path = f"{self.target_path}/{self.target_docker_env}"
        self.exec.fs_create_empty_file(conn, env_path)
        self.exec.fs_append_line(
            conn, env_path, f"TRAEFIK_USER_AND_PW={self.user}:{self.hashed_pw}"
        )
        self.exec.fs_append_line(conn, env_path, f"MLSERVER_ENDPOINT_URL={conn.host}")
        self.exec.fs_append_line(conn, env_path, f"MLSERVER_ENDPOINT_PORT={self.port}")
        self.exec.fs_append_line(conn, env_path, f"MLFLOW_REMOTE_MODEL={self.model}")
        self.exec.fs_append_line(conn, env_path, f"MLFLOW_REMOTE_URI={self.tracking_uri}")
        self.exec.fs_append_line(conn, env_path, f"MLFLOW_REMOTE_USER={self.tracking_user}")
        self.exec.fs_append_line(conn, env_path, f"MLFLOW_REMOTE_PW={self.tracking_pw}")
        self.exec.fs_append_line(conn, env_path, "MLFLOW_REMOTE_INSECURE=true")
        self.service_ports["MLServer REST API"] = int(self.port)
        self.service_urls["MLServer REST API"] = f"https://{conn.host}:{self.port}"
        self.service_url = f"https://{conn.host}:{self.port}"

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
        return {}

    def get_secrets(self) -> Dict[str, Dict]:
        secrets: Dict[str, Dict] = {}

        basic_auth = {
            key: value
            for key, value in {
                "username": self.user,
                "password": self.pw,
            }.items()
            if value
        }
        if basic_auth:
            secrets["mlserver_basic_auth"] = basic_auth

        tracking_auth = {
            key: value
            for key, value in {
                "username": self.tracking_user,
                "password": self.tracking_pw,
            }.items()
            if value
        }
        if tracking_auth:
            secrets["mlflow_tracking_credentials"] = tracking_auth

        return secrets
