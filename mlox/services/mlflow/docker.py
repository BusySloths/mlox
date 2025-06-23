import logging

from dataclasses import dataclass, field
from typing import Dict

from mlox.service import AbstractService, tls_setup_no_config
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
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)


@dataclass
class MLFlowDockerService(AbstractService):
    ui_user: str
    ui_pw: str
    port: str | int
    service_url: str = field(init=False, default="")

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

    def check(self, conn) -> Dict:
        """
        Check if the MLFlow service is running and accessible.
        Returns a dictionary with the status and any relevant information.
        """
        try:
            response = conn.run(
                f"curl -s -o /dev/null -w '%{{http_code}}' http://{conn.host}:{self.port}/",
                hide=True,
            )
            if response.stdout.strip() == "200":
                return {
                    "status": "running",
                    "message": "MLFlow service is up and running.",
                }
            else:
                return {
                    "status": "down",
                    "message": f"MLFlow service returned HTTP status {response.stdout.strip()}.",
                }
        except Exception as e:
            return {"status": "error", "message": str(e)}
