import logging

from dataclasses import dataclass, field
from typing import Dict, Any

from mlox.service import AbstractService


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
        self.exec.fs_create_dir(conn, self.target_path)
        self.exec.fs_copy(conn, self.template, f"{self.target_path}/{self.target_docker_script}")
        self.exec.fs_copy(conn, self.ollama_script, f"{self.target_path}/entrypoint.sh")
        self.exec.fs_copy(conn, self.litellm_config, f"{self.target_path}/litellm-config.yaml")
        self.exec.tls_setup(conn, conn.host, self.target_path)
        base_url = f"https://{conn.host}:{self.ui_port}/ui"
        env_path = f"{self.target_path}/{self.target_docker_env}"
        self.exec.fs_create_empty_file(conn, env_path)
        self.exec.fs_append_line(conn, env_path, f"MY_LITELLM_MASTER_KEY={self.api_key}")
        self.exec.fs_append_line(conn, env_path, f"MY_LITELLM_SLACK_WEBHOOK={self.slack_webhook}")
        self.exec.fs_append_line(conn, env_path, f"MY_LITELLM_PORT={self.ui_port}")
        self.exec.fs_append_line(conn, env_path, f"MY_LITELLM_SERVICE_PORT={self.service_port}")
        self.exec.fs_append_line(conn, env_path, f"MY_LITELLM_USERNAME={self.ui_user}")
        self.exec.fs_append_line(conn, env_path, f"MY_LITELLM_PASSWORD={self.ui_pw}")
        self.service_urls["LiteLLM UI"] = base_url
        self.service_urls["LiteLLM Service"] = (
            f"https://{conn.host}:{self.service_port}"
        )

        self.service_ports["LiteLLM UI"] = int(self.ui_port)
        self.service_ports["LiteLLM Service"] = int(self.service_port)
        self.state = "running"

    def teardown(self, conn):
        self.exec.docker_down(
            conn,
            f"{self.target_path}/{self.target_docker_script}",
            remove_volumes=True,
        )
        self.exec.fs_delete_dir(conn, self.target_path)
        self.state = "un-initialized"

    def spin_up(self, conn) -> bool:
        return self.compose_up(conn)

    def spin_down(self, conn) -> bool:
        return self.compose_down(conn)

    def check(self, conn) -> Dict:
        return dict()

    def get_secrets(self) -> Dict[str, Dict]:
        secrets: Dict[str, Dict] = {}

        if self.api_key:
            secrets["litellm_api_access"] = {"api_key": self.api_key}

        if self.slack_webhook:
            secrets["litellm_slack_alerting"] = {"webhook_url": self.slack_webhook}

        credentials = {
            key: value
            for key, value in {
                "username": self.ui_user,
                "password": self.ui_pw,
            }.items()
            if value
        }
        if credentials:
            secrets["litellm_ui_credentials"] = credentials

        return secrets
