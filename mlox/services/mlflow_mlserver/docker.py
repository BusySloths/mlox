"""Docker deployment adapter for MLflow + MLServer inference stacks.

Purpose:
- Provision combined tracking and model-serving containers for MLflow/MLServer workflows.

Key public classes/functions:
- ``MLFlowMLServerDockerService``

Expected runtime mode:
- Remote executor (invoked from CLI/UI/TUI orchestration)

Related modules (plain-text links):
- mlox.service
- mlox.services.mlflow_mlserver.ui
- mlox.services.mlflow
"""

import logging
import os
import shlex

from typing import Dict, cast
from passlib.hash import apr_md5_crypt  # type: ignore
from dataclasses import dataclass, field

from mlox.infra import ModelRegistry, ModelServer
from mlox.service import AbstractService
from mlox.executors import TaskGroup

logger = logging.getLogger(__name__)


@dataclass
class MLFlowMLServerDockerService(AbstractService, ModelServer):
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
        self.exec.fs_copy(
            conn, self.template, f"{self.target_path}/{self.target_docker_script}"
        )
        self.exec.fs_copy(
            conn,
            self.dockerfile,
            f"{self.target_path}/{os.path.basename(self.dockerfile)}",
        )
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
        self.exec.fs_append_line(
            conn, env_path, f"MLFLOW_REMOTE_URI={self.tracking_uri}"
        )
        self.exec.fs_append_line(
            conn, env_path, f"MLFLOW_REMOTE_USER={self.tracking_user}"
        )
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
        try:
            state = self.exec.docker_service_state(
                conn, self.compose_service_names.get("MLServer", "")
            )
            if state and state.strip() == "running":
                health_url = f"{self.service_url}/v2/health/ready"
                host = shlex.quote(conn.host)
                user = shlex.quote(self.user)
                pw = shlex.quote(self.pw)
                url = shlex.quote(health_url)
                cmd = (
                    "curl -s -o /dev/null -w '%{http_code}' -k "
                    f"-u {user}:{pw} -H 'Host: {host}' {url}"
                )
                code = self.exec.execute(
                    conn,
                    command=cmd,
                    group=TaskGroup.NETWORKING,
                    description="Check MLServer readiness",
                )
                if code and code.strip() == "200":
                    self.state = "running"
                    return {"status": "running"}
                self.state = "unknown"
                return {"status": "unknown", "http_code": (code or "").strip()}
            self.state = "stopped"
            return {"status": "stopped"}
        except Exception as exc:  # pragma: no cover - defensive logging path
            logger.error("Error checking MLServer status: %s", exc)
            self.state = "unknown"
        return {"status": "unknown"}

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

    def get_registry(self) -> ModelRegistry | None:
        if not self.registry_uuid:
            logger.warning("No registry UUID set for MLFlow MLServer service.")
            return None
        svc = cast(AbstractService, self)  # type: ignore
        registry = svc.get_dependent_service(self.registry_uuid)
        if not registry:
            logger.warning("No registry service found for UUID %s", self.registry_uuid)
            return None
        return cast(ModelRegistry, registry)  # type: ignore

    def is_model(self, name: str) -> bool:
        if ":" in name:
            parts = name.split(":")
            if len(parts) != 3:
                return False
            registry_name, model_name, version = parts
            registry_service = self.get_dependent_service_by_name(registry_name)
            if not registry_service:
                return False
            full_model_name = f"{model_name}/{version}"
            return full_model_name == self.model
        return name == self.model
