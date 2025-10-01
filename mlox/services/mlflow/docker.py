import os
import mlflow  # type: ignore
import logging

from dataclasses import dataclass, field
from typing import Dict

from mlox.service import AbstractService
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
logger = logging.getLogger(__name__)


@dataclass
class MLFlowDockerService(AbstractService):
    ui_user: str
    ui_pw: str
    port: str | int
    service_url: str = field(init=False, default="")
    compose_service_names: Dict[str, str] = field(
        init=False,
        default_factory=lambda: {"Traefik": "traefik", "MLflow": "mlflow"},
    )

    def setup(self, conn) -> None:
        fs_create_dir(conn, self.target_path)
        fs_copy(conn, self.template, f"{self.target_path}/{self.target_docker_script}")
        env_path = f"{self.target_path}/{self.target_docker_env}"
        fs_create_empty_file(conn, env_path)
        fs_append_line(conn, env_path, f"MLFLOW_PORT={self.port}")
        fs_append_line(conn, env_path, f"MLFLOW_URL={conn.host}")
        fs_append_line(conn, env_path, f"MLFLOW_USERNAME={self.ui_user}")
        fs_append_line(conn, env_path, f"MLFLOW_PASSWORD={self.ui_pw}")
        # fs_append_line(conn, env_path, f"MLFLOW_TRACKING_USERNAME={self.ui_user}")
        # fs_append_line(conn, env_path, f"MLFLOW_TRACKING_PASSWORD={self.ui_pw}")
        ini_path = f"{self.target_path}/basic-auth.ini"
        fs_create_empty_file(conn, ini_path)
        fs_append_line(conn, ini_path, "[mlflow]")
        fs_append_line(conn, ini_path, "default_permission = READ")
        fs_append_line(conn, ini_path, "database_uri = sqlite:///basic_auth.db")
        fs_append_line(conn, ini_path, f"admin_username = {self.ui_user}")
        fs_append_line(conn, ini_path, f"admin_password = {self.ui_pw}")
        self.service_ports["MLFlow Webserver"] = int(self.port)
        self.service_urls["MLFlow UI"] = f"https://{conn.host}:{self.port}"
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
        """
        Check if the MLFlow service is running and accessible.
        Returns a dictionary with the status and some basic stats from the MLflow server.
        """
        # Primary approach: use the mlflow client API for a structured health check
        try:
            mlflow.set_registry_uri(self.service_url)
            os.environ["MLFLOW_TRACKING_USERNAME"] = self.ui_user
            os.environ["MLFLOW_TRACKING_PASSWORD"] = self.ui_pw
            os.environ["MLFLOW_TRACKING_INSECURE_TLS"] = "true"
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
            }.items()
            if value
        }
        if not credentials:
            return {}
        return {"mlflow_ui_credentials": credentials}
