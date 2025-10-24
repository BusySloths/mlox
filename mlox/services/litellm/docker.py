import logging

from dataclasses import dataclass, field
from typing import Dict, Any, List

import yaml

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
    openai_key: str
    ollama_models: List[str] = field(default_factory=list)
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
        self.exec.fs_copy(
            conn, self.template, f"{self.target_path}/{self.target_docker_script}"
        )
        self.exec.fs_copy(conn, self.ollama_script, f"{self.target_path}/entrypoint.sh")
        self.write_litellm_config(conn, self.ollama_models, self.openai_key)
        self.exec.tls_setup(conn, conn.host, self.target_path)

        env_path = f"{self.target_path}/{self.target_docker_env}"
        self.exec.fs_create_empty_file(conn, env_path)
        self.exec.fs_append_line(
            conn, env_path, f"MY_LITELLM_MASTER_KEY={self.api_key}"
        )
        self.exec.fs_append_line(
            conn, env_path, f"MY_LITELLM_SLACK_WEBHOOK={self.slack_webhook}"
        )
        self.exec.fs_append_line(conn, env_path, f"MY_LITELLM_PORT={self.ui_port}")
        self.exec.fs_append_line(
            conn, env_path, f"MY_LITELLM_SERVICE_PORT={self.service_port}"
        )
        self.exec.fs_append_line(conn, env_path, f"MY_LITELLM_USERNAME={self.ui_user}")
        self.exec.fs_append_line(conn, env_path, f"MY_LITELLM_PASSWORD={self.ui_pw}")
        self.exec.fs_append_line(conn, env_path, f"MY_LITELLM_PUBLIC_HOST={conn.host}")
        self.exec.fs_append_line(conn, env_path, f"MY_LITELLM_NAME={self.name}")

        # Add Ollama models configuration
        models = ",".join(self.ollama_models) if len(self.ollama_models) > 0 else ""
        self.exec.fs_append_line(conn, env_path, f"MY_OLLAMA_MODELS={models}")

        self.compose_service_names = {
            "LiteLLM": f"{self.name}-litellm",
            "LiteLLM Database": f"{self.name}-postgres",
            "LiteLLM Redis": f"{self.name}-redis",
            "Ollama": f"{self.name}-ollama",
        }

        self.service_urls["Login"] = (
            f"https://{conn.host}:{self.ui_port}/fallback/login"
        )
        self.service_urls["Service"] = f"https://{conn.host}:{self.service_port}"
        self.service_ports["Service"] = int(self.service_port)
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
        services: Dict[str, str] = {}
        try:
            for label, service in self.compose_service_names.items():
                docker_state = self.exec.docker_service_state(conn, service)
                services[label] = docker_state or "unknown"
        except Exception as exc:
            logging.error("Error retrieving LiteLLM service state: %s", exc)
            self.state = "unknown"
            return {"status": "unknown", "services": services}

        if services and all(state == "running" for state in services.values()):
            status = "running"
        elif any(state in {"created", "restarting"} for state in services.values()):
            status = "starting"
        elif services and all(state == "exited" for state in services.values()):
            status = "stopped"
        else:
            status = "unknown"

        if status == "running":
            self.state = "running"
        elif status == "stopped":
            self.state = "stopped"
        elif status == "starting":
            self.state = "running"
        else:
            self.state = "unknown"

        return {"status": status, "services": services}

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

    def write_litellm_config(
        self, conn, ollama_models: List[str], openai_api_key: str = ""
    ) -> None:
        """Generate a LiteLLM config based on selected models and optional OpenAI access."""
        config_path = f"{self.target_path}/litellm-config.yaml"

        config: Dict[str, Any] = {
            "model_list": [],
            "router_settings": {
                "redis_host": "redis",
                "redis_password": "SDsdgFsfm4lmf43lfnm34lkf",
                "redis_port": 6379,
            },
        }

        # Build Ollama model entries while preserving order and removing duplicates
        deduped_models = list(dict.fromkeys(ollama_models))

        for model in deduped_models:
            # Allow users to specify fully-qualified provider models (e.g. "ollama/tinyllama").
            # When no provider prefix is given, default to Ollama.
            # backend_model = model if "/" in model else f"ollama/{model}"
            display_name = model.split("/", 1)[-1] if "/" in model else model
            config["model_list"].append(
                {
                    "model_name": display_name,
                    "litellm_params": {
                        "model": f"ollama/{display_name}",
                        "api_base": "http://ollama:11434",
                    },
                }
            )

        if openai_api_key:
            config["model_list"].append(
                {
                    "model_name": "gpt-4o-mini",
                    "litellm_params": {
                        "model": "gpt-4o-mini",
                        "api_key": openai_api_key,
                    },
                }
            )

        config_content = yaml.safe_dump(config, sort_keys=False)
        self.exec.fs_write_file(conn, config_path, config_content)
