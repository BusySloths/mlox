"""Docker deployment adapter for standalone Ollama services."""

import logging
import shlex

from dataclasses import dataclass, field
from typing import Dict, List

from passlib.hash import apr_md5_crypt  # type: ignore

from mlox.executors import TaskGroup
from mlox.service import AbstractService

logger = logging.getLogger(__name__)


@dataclass
class OllamaDockerService(AbstractService):
    port: str | int
    user: str = "admin"
    pw: str = "s3cr3t"
    ollama_models: List[str] = field(default_factory=list)
    keep_alive: str = "24h"
    ollama_script: str = ""
    hashed_pw: str = field(default="", init=False)
    service_url: str = field(init=False, default="")
    compose_service_names: Dict[str, str] = field(init=False, default_factory=dict)

    def __post_init__(self) -> None:
        super().__post_init__()
        if not self.target_path.endswith(f"-{self.port}"):
            self.target_path = f"{self.target_path}-{self.port}"
        self.compose_service_names = {
            "Traefik": f"traefik_reverse_proxy_ollama_{self.port}",
            "Ollama": f"ollama_{self.port}",
        }

    def _generate_htpasswd_entry(self) -> None:
        self.hashed_pw = apr_md5_crypt.hash(self.pw).replace("$", "$$")

    def setup(self, conn) -> None:
        self.exec.fs_create_dir(conn, self.target_path)
        self.exec.fs_copy(
            conn, self.template, f"{self.target_path}/{self.target_docker_script}"
        )
        if self.ollama_script:
            self.exec.fs_copy(conn, self.ollama_script, f"{self.target_path}/entrypoint.sh")

        self._generate_htpasswd_entry()

        env_path = f"{self.target_path}/{self.target_docker_env}"
        self.exec.fs_create_empty_file(conn, env_path)
        self.exec.fs_append_line(
            conn, env_path, f"TRAEFIK_USER_AND_PW={self.user}:{self.hashed_pw}"
        )
        self.exec.fs_append_line(conn, env_path, f"OLLAMA_ENDPOINT_URL={conn.host}")
        self.exec.fs_append_line(conn, env_path, f"OLLAMA_ENDPOINT_PORT={self.port}")
        self.exec.fs_append_line(conn, env_path, f"OLLAMA_KEEP_ALIVE={self.keep_alive}")

        models = ",".join(dict.fromkeys(self.ollama_models))
        self.exec.fs_append_line(conn, env_path, f"MY_OLLAMA_MODELS={models}")

        self.service_ports["Ollama API"] = int(self.port)
        self.service_urls["Ollama API"] = f"https://{conn.host}:{self.port}"
        self.service_url = f"https://{conn.host}:{self.port}"
        self.state = "running"

    def teardown(self, conn):
        self.exec.docker_down(
            conn,
            f"{self.target_path}/{self.target_docker_script}",
            f"{self.target_path}/{self.target_docker_env}",
            remove_volumes=True,
        )
        self.exec.fs_delete_dir(conn, self.target_path)
        self.state = "un-initialized"

    def spin_up(self, conn) -> bool:
        return self.compose_up(conn)

    def spin_down(self, conn) -> bool:
        return self.compose_down(conn)

    def check(self, conn) -> Dict:
        try:
            state = self.exec.docker_service_state(
                conn, self.compose_service_names.get("Ollama", "")
            )
            if state and state.strip() == "running":
                host = shlex.quote(conn.host)
                user = shlex.quote(self.user)
                pw = shlex.quote(self.pw)
                url = shlex.quote(f"{self.service_url}/api/tags")
                cmd = (
                    "curl -s -o /dev/null -w '%{http_code}' -k "
                    f"-u {user}:{pw} -H 'Host: {host}' {url}"
                )
                code = self.exec.execute(
                    conn,
                    command=cmd,
                    group=TaskGroup.NETWORKING,
                    description="Check Ollama API",
                )
                if code and code.strip() == "200":
                    self.state = "running"
                    return {"status": "running"}
                self.state = "unknown"
                return {"status": "unknown", "http_code": (code or "").strip()}
            self.state = "stopped"
            return {"status": "stopped"}
        except Exception as exc:  # pragma: no cover - defensive logging path
            logger.error("Error checking Ollama status: %s", exc)
            self.state = "unknown"
        return {"status": "unknown"}

    def get_secrets(self) -> Dict[str, Dict]:
        return {
            "ollama_basic_auth": {
                "username": self.user,
                "password": self.pw,
                "service_url": self.service_url,
            }
        }
