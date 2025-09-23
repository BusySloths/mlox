import logging

from dataclasses import dataclass, field
from typing import Dict, Any

from mlox.service import AbstractService, tls_setup
from mlox.remote import (
    fs_copy,
    fs_read_file,
    fs_touch,
    fs_delete_dir,
    fs_create_dir,
    fs_create_empty_file,
    fs_find_and_replace,
    fs_append_line,
    docker_down,
    exec_command,
)

# Configure logging (optional, but recommended)
logging.basicConfig(
    level=logging.INFO,
    format="[%(levelname)s] %(asctime)s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)


@dataclass
class LiteLLMDockerService(AbstractService):
    ollama_script: str
    litellm_config: str
    ui_user: str
    ui_pw: str
    ui_port: str | int
    service_port: str | int
    slack_webhook: str
    api_key: str
    compose_service_names: Dict[str, str] = field(
        init=False,
        default_factory=lambda: {
            "LiteLLM": "litellm",
            "LiteLLM Database": "postgres",
            "LiteLLM Redis": "redis",
            "Ollama": "ollama",
        },
    )

    def setup(self, conn) -> None:
        # copy files to target
        fs_create_dir(conn, self.target_path)
        fs_copy(conn, self.template, f"{self.target_path}/{self.target_docker_script}")
        fs_copy(conn, self.ollama_script, f"{self.target_path}/entrypoint.sh")
        fs_copy(conn, self.litellm_config, f"{self.target_path}/litellm-config.yaml")
        tls_setup(conn, conn.host, self.target_path)
        base_url = f"https://{conn.host}:{self.ui_port}/ui"
        env_path = f"{self.target_path}/{self.target_docker_env}"
        fs_create_empty_file(conn, env_path)
        fs_append_line(conn, env_path, f"MY_LITELLM_MASTER_KEY={self.api_key}")
        fs_append_line(conn, env_path, f"MY_LITELLM_SLACK_WEBHOOK={self.slack_webhook}")
        fs_append_line(conn, env_path, f"MY_LITELLM_PORT={self.ui_port}")
        fs_append_line(conn, env_path, f"MY_LITELLM_SERVICE_PORT={self.service_port}")
        fs_append_line(conn, env_path, f"MY_LITELLM_USERNAME={self.ui_user}")
        fs_append_line(conn, env_path, f"MY_LITELLM_PASSWORD={self.ui_pw}")
        self.service_urls["LiteLLM UI"] = base_url
        self.service_urls["LiteLLM Service"] = (
            f"https://{conn.host}:{self.service_port}"
        )

        self.service_ports["LiteLLM UI"] = int(self.ui_port)
        self.service_ports["LiteLLM Service"] = int(self.service_port)
        self.state = "running"

    def teardown(self, conn):
        docker_down(
            conn,
            f"{self.target_path}/{self.target_docker_script}",
            remove_volumes=True,
        )
        fs_delete_dir(conn, self.target_path)
        self.state = "un-initialized"

    def spin_up(self, conn) -> bool:
        return self.compose_up(conn)

    def spin_down(self, conn) -> bool:
        return self.compose_down(conn)

    def check(self, conn) -> Dict:
        return dict()
