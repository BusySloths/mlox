"""Docker deployment adapter for the lightweight MLflow registry gateway."""

import logging
import os
import shlex

from dataclasses import dataclass, field
from typing import Dict, cast

from passlib.hash import apr_md5_crypt  # type: ignore

from mlox.executors import TaskGroup
from mlox.service import (
    AbstractModelRegistryService,
    AbstractModelServerService,
    AbstractService,
)

logger = logging.getLogger(__name__)


def _resolved_text(value: str) -> str:
    if value.strip().startswith("${") and value.strip().endswith("}"):
        return ""
    return value


def _resolved_setting(value: str | int | float, default: str) -> str:
    resolved = _resolved_text(str(value))
    return resolved or default


@dataclass
class MLFlowGatewayDockerService(AbstractService, AbstractModelServerService):
    dockerfile: str
    serve_script: str
    start_script: str
    port: str | int
    tracking_uri: str
    tracking_user: str
    tracking_pw: str
    requirements_txt: str = ""
    cache_max_models: str | int = "10"
    cache_ttl_days: str | int | float = "10"
    user: str = "admin"
    pw: str = "s3cr3t"
    hashed_pw: str = field(default="", init=False)
    service_url: str = field(init=False, default="")
    compose_service_names: Dict[str, str] = field(init=False, default_factory=dict)

    def __post_init__(self) -> None:
        super().__post_init__()
        if not self.target_path.endswith(f"-{self.port}"):
            self.target_path = f"{self.target_path}-{self.port}"
        self.compose_service_names = {
            "Traefik": f"traefik_reverse_proxy_mlflow_gateway_{self.port}",
            "MLflow Gateway": f"mlflow_gateway_{self.port}",
        }

    def _generate_htpasswd_entry(self) -> None:
        self.hashed_pw = apr_md5_crypt.hash(self.pw).replace("$", "$$")

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
        self.exec.fs_copy(conn, self.serve_script, f"{self.target_path}/serve.py")
        self.exec.fs_copy(
            conn,
            self.start_script,
            f"{self.target_path}/{os.path.basename(self.start_script)}",
        )
        self.exec.fs_write_file(
            conn,
            f"{self.target_path}/gateway-requirements.txt",
            _resolved_text(self.requirements_txt or ""),
        )

        self._generate_htpasswd_entry()

        env_path = f"{self.target_path}/{self.target_docker_env}"
        self.exec.fs_create_empty_file(conn, env_path)
        self.exec.fs_append_line(
            conn, env_path, f"TRAEFIK_USER_AND_PW={self.user}:{self.hashed_pw}"
        )
        self.exec.fs_append_line(conn, env_path, f"MLFLOW_GATEWAY_URL={conn.host}")
        self.exec.fs_append_line(conn, env_path, f"MLFLOW_GATEWAY_PORT={self.port}")
        self.exec.fs_append_line(conn, env_path, f"MLFLOW_REMOTE_URI={self.tracking_uri}")
        self.exec.fs_append_line(conn, env_path, f"MLFLOW_REMOTE_USER={self.tracking_user}")
        self.exec.fs_append_line(conn, env_path, f"MLFLOW_REMOTE_PW={self.tracking_pw}")
        self.exec.fs_append_line(conn, env_path, "MLFLOW_REMOTE_INSECURE=true")
        self.exec.fs_append_line(
            conn,
            env_path,
            "MLOX_GATEWAY_CACHE_MAX_MODELS="
            f"{_resolved_setting(self.cache_max_models, '10')}",
        )
        self.exec.fs_append_line(
            conn,
            env_path,
            f"MLOX_GATEWAY_CACHE_TTL_DAYS={_resolved_setting(self.cache_ttl_days, '10')}",
        )

        self.service_ports["MLflow Gateway REST API"] = int(self.port)
        self.service_urls["MLflow Gateway REST API"] = f"https://{conn.host}:{self.port}"
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
                conn, self.compose_service_names.get("MLflow Gateway", "")
            )
            if state and state.strip() == "running":
                host = shlex.quote(conn.host)
                user = shlex.quote(self.user)
                pw = shlex.quote(self.pw)
                url = shlex.quote(f"{self.service_url}/health")
                cmd = (
                    "curl -s -o /dev/null -w '%{http_code}' -k "
                    f"-u {user}:{pw} -H 'Host: {host}' {url}"
                )
                code = self.exec.execute(
                    conn,
                    command=cmd,
                    group=TaskGroup.NETWORKING,
                    description="Check MLflow Gateway health",
                )
                if code and code.strip() == "200":
                    self.state = "running"
                    return {"status": "running"}
                self.state = "unknown"
                return {"status": "unknown", "http_code": (code or "").strip()}
            self.state = "stopped"
            return {"status": "stopped"}
        except Exception as exc:  # pragma: no cover - defensive logging path
            logger.error("Error checking MLflow Gateway status: %s", exc)
            self.state = "unknown"
        return {"status": "unknown"}

    def get_secrets(self) -> Dict[str, Dict]:
        secrets: Dict[str, Dict] = {}
        secrets["mlflow_gateway_basic_auth"] = {
            "username": self.user,
            "password": self.pw,
            "service_url": self.service_url,
        }
        secrets["mlflow_tracking_credentials"] = {
            "username": self.tracking_user,
            "password": self.tracking_pw,
            "tracking_uri": self.tracking_uri,
            "cache_max_models": str(self.cache_max_models),
            "cache_ttl_days": str(self.cache_ttl_days),
        }
        return secrets

    def get_registry(self) -> AbstractModelRegistryService | None:
        if not self.registry_uuid:
            logger.warning("No registry UUID set for MLflow Gateway service.")
            return None
        svc = cast(AbstractService, self)  # type: ignore
        registry = svc.get_dependent_service(self.registry_uuid)
        if not registry:
            logger.warning("No registry service found for UUID %s", self.registry_uuid)
            return None
        return cast(AbstractModelRegistryService, registry)  # type: ignore

    def is_model(self, name: str) -> bool:
        if ":" not in name:
            return False
        parts = name.split(":")
        if len(parts) != 3:
            return False
        registry_name, model_name, version = parts
        registry_service = self.get_dependent_service_by_name(registry_name)
        if not registry_service:
            return False
        return bool(model_name and version)
