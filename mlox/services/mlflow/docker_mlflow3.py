import mlflow  # type: ignore
import logging

from typing import Any, Dict, List
from datetime import datetime
from dataclasses import dataclass, field

from mlox.service import (
    AbstractModelRegistryService,
    AbstractService,
    AbstractWebUIService,
    ServiceCapability,
)
from mlox.services.mlflow.artifacts import (
    configure_mlflow_client,
    load_registered_model_json_artifact,
)

logger = logging.getLogger(__name__)


def _fmt_ts(ts: int | None) -> str:
    if not ts:
        return ""
    return datetime.utcfromtimestamp(ts / 1000).strftime("%Y-%m-%d %H:%M")


@dataclass
class MLFlow3DockerService(
    AbstractService, AbstractModelRegistryService, AbstractWebUIService
):
    capabilities = {ServiceCapability.MODEL_REGISTRY, ServiceCapability.WEB_UI}
    web_ui_url_label = "MLFlow UI"
    web_ui_login_fields = ("username", "password")
    ui_user: str
    ui_pw: str
    port: str | int
    service_url: str = field(init=False, default="")
    compose_service_names: Dict[str, str] = field(
        init=False,
        default_factory=lambda: {"Traefik": "traefik", "MLflow": "mlflow"},
    )

    def setup(self, conn) -> None:
        self.exec.fs_create_dir(conn, self.target_path)
        self.exec.fs_copy(
            conn, self.template, f"{self.target_path}/{self.target_docker_script}"
        )
        env_path = f"{self.target_path}/{self.target_docker_env}"
        self.exec.fs_create_empty_file(conn, env_path)
        self.exec.fs_append_line(conn, env_path, f"MLFLOW_PORT={self.port}")
        self.exec.fs_append_line(conn, env_path, f"MLFLOW_URL={conn.host}")
        self.exec.fs_append_line(conn, env_path, f"MLFLOW_USERNAME={self.ui_user}")
        self.exec.fs_append_line(conn, env_path, f"MLFLOW_PASSWORD={self.ui_pw}")
        ini_path = f"{self.target_path}/basic-auth.ini"
        self.exec.fs_create_empty_file(conn, ini_path)
        self.exec.fs_append_line(conn, ini_path, "[mlflow]")
        self.exec.fs_append_line(conn, ini_path, "default_permission = READ")
        self.exec.fs_append_line(
            conn, ini_path, "database_uri = sqlite:///basic_auth.db"
        )
        self.exec.fs_append_line(conn, ini_path, f"admin_username = {self.ui_user}")
        self.exec.fs_append_line(conn, ini_path, f"admin_password = {self.ui_pw}")
        self.service_ports["MLFlow Webserver"] = int(self.port)
        self.service_urls["MLFlow UI"] = f"https://{conn.host}:{self.port}"
        self.service_urls["Dashboard"] = f"https://{conn.host}:{self.port}"
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
        """
        Check if the MLFlow service is running and accessible.
        Returns a dictionary with the status and some basic stats from the MLflow server.
        """
        # Primary approach: use the mlflow client API for a structured health check
        try:
            configure_mlflow_client(self.service_url, self.ui_user, self.ui_pw)
            client = mlflow.tracking.MlflowClient()

            models = client.search_registered_models(filter_string="", max_results=10)
            return {
                "status": "running",
                "message": "MLflow API reachable",
                "registered_models (cutoff=10)": len(models),
            }
        except Exception as e_ml:
            logger.debug("MLflow API check failed: %s", e_ml)
        return {
            "status": "unknown",
            "message": "MLflow API not reachable",
        }

    def get_secrets(self) -> Dict[str, Dict]:
        credentials = {
            key: value
            for key, value in {
                "username": self.ui_user,
                "password": self.ui_pw,
                "service_url": self.service_url,
                "port": str(self.port),
                "insecure_tls": "true",
            }.items()
            if value
        }
        if not credentials:
            return {}
        return credentials

    def list_models(self, filter: str | None = None) -> List[Dict[str, Any]]:
        """List all registered model names from the MLflow server."""
        all_models = []
        try:
            configure_mlflow_client(self.service_url, self.ui_user, self.ui_pw)

            client = mlflow.tracking.MlflowClient()
            models = client.search_model_versions(
                filter_string=filter or "", max_results=250
            )
            for m in models:
                all_models.append(
                    {
                        "Model": m.name,
                        "Description": m.description or "",
                        "Version": m.version,
                        "Stage": m.current_stage or "-",
                        "Aliases": ", ".join(m.aliases or []),
                        "Status": m.status,
                        "Tags": m.tags or {},
                        "Updated": _fmt_ts(m.last_updated_timestamp),
                        "Run ID": m.run_id,
                        "Open": f"{self.service_url}#/models/{m.name}/versions/{m.version}",
                    }
                )

        except Exception as e:
            logger.error("Error listing models from MLflow: %s", e)
        return all_models

    def load_artifact(
        self,
        model_name: str,
        model_version: str,
        artifact_path: str,
    ) -> Any | None:
        try:
            return load_registered_model_json_artifact(
                service_url=self.service_url,
                username=self.ui_user,
                password=self.ui_pw,
                model_name=model_name,
                model_version=model_version,
                artifact_path=artifact_path,
            )
        except Exception as exc:
            logger.debug("Could not load MLflow artifact %s: %s", artifact_path, exc)
            return None
