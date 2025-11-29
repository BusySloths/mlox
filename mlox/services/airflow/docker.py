import ssl
import json
import base64
import logging
import urllib.request

from typing import Dict
from dataclasses import dataclass, field

from mlox.service import AbstractService
from mlox.utils import generate_password


logger = logging.getLogger(__name__)


@dataclass
class AirflowDockerService(AbstractService):
    path_dags: str
    path_output: str
    ui_user: str
    ui_pw: str
    port: str
    secret_path: str = ""
    secret_key: str = field(
        default="9d54873d8b53466dbcfd00a2bb9a104caa8071143f864aa88c36d3f5a8c8615f",
        init=False,
    )
    compose_service_names: Dict[str, str] = field(
        init=False,
        default_factory=lambda: {
            "Airflow Webserver": "airflow-webserver",
            "Airflow Scheduler": "airflow-scheduler",
            "Airflow Worker": "airflow-worker",
            "Airflow Triggerer": "airflow-triggerer",
            "Airflow DAG Processor": "airflow-dag-processor",
            "Airflow Initializer": "airflow-init",
            "Airflow CLI": "airflow-cli",
            "Postgres": "postgres",
            "Redis": "redis",
        },
    )

    def __str__(self):
        return f"AirflowDockerService(path_dags={self.path_dags}, path_output={self.path_output}, ui_user={self.ui_user}, ui_pw={self.ui_pw}, port={self.port}, secret_path={self.secret_path})"

    def setup(self, conn) -> None:
        # copy files to target
        self.exec.fs_create_dir(conn, self.target_path)
        # Ensure host directories for DAGs and logs/outputs exist and are owned by mlox_user
        # This is crucial for volume mounts to have correct permissions for AIRFLOW_UID.
        self.exec.fs_create_dir(conn, self.path_dags)
        self.exec.fs_create_dir(conn, self.path_output)
        # self.exec.fs_create_dir(conn, self.target_path + "/logs")
        # self.exec.fs_create_dir(conn, self.target_path + "/plugins")

        self.exec.fs_copy(
            conn, self.template, f"{self.target_path}/{self.target_docker_script}"
        )
        self.exec.tls_setup(conn, conn.host, self.target_path)
        # setup environment
        base_url = f"https://{conn.host}:{self.port}"
        if len(self.secret_path) >= 1:
            base_url = f"https://{conn.host}:{self.port}/{self.secret_path}"
        env_path = f"{self.target_path}/{self.target_docker_env}"
        self.exec.fs_create_empty_file(conn, env_path)
        self.exec.fs_append_line(conn, env_path, "_AIRFLOW_SSL_CERT_NAME=cert.pem")
        self.exec.fs_append_line(conn, env_path, "_AIRFLOW_SSL_KEY_NAME=key.pem")
        self.exec.fs_append_line(
            conn, env_path, f"AIRFLOW_UID={self.exec.sys_user_id(conn)}"
        )
        self.secret_key = generate_password(length=48)
        self.exec.fs_append_line(conn, env_path, f"_AIRFLOW_SECRET={self.secret_key}")
        self.exec.fs_append_line(
            conn, env_path, f"_AIRFLOW_SSL_FILE_PATH={self.target_path}/"
        )
        self.exec.fs_append_line(conn, env_path, f"_AIRFLOW_OUT_PORT={self.port}")
        self.exec.fs_append_line(conn, env_path, f"_AIRFLOW_BASE_URL={base_url}")
        self.exec.fs_append_line(conn, env_path, f"_AIRFLOW_LOG_HOST={base_url}")
        self.exec.fs_append_line(
            conn, env_path, f"_AIRFLOW_WWW_USER_USERNAME={self.ui_user}"
        )
        self.exec.fs_append_line(
            conn, env_path, f"_AIRFLOW_WWW_USER_PASSWORD={self.ui_pw}"
        )
        self.exec.fs_append_line(
            conn, env_path, f"_AIRFLOW_OUT_FILE_PATH={self.path_output}"
        )
        self.exec.fs_append_line(
            conn, env_path, f"_AIRFLOW_DAGS_FILE_PATH={self.path_dags}"
        )
        self.exec.fs_append_line(conn, env_path, "_AIRFLOW_LOAD_EXAMPLES=false")
        self.service_urls["Airflow UI"] = base_url
        self.service_ports["Airflow Webserver"] = int(self.port)

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
        return self.compose_down(conn, remove_volumes=True)

    def check(self, conn) -> Dict:
        """
        Checks if the Airflow API is responsive using the /api/v2/version endpoint.
        This corresponds to the health check from the docker-compose file:
        `curl --fail "${_AIRFLOW_BASE_URL:-http://localhost:8080}/api/v2/version"`
        """
        url = self.service_urls["Airflow UI"] + "/api/v2/version"
        logger.info(f"Performing health check on Airflow service at {url}")

        try:
            # Create an SSL context that does not verify certificates. This is
            # necessary for self-signed certificates used in local/dev setups.
            ssl_context = ssl._create_unverified_context()
            request = urllib.request.Request(url)
            # Airflow's REST API uses Basic Authentication.
            auth_string = f"{self.ui_user}:{self.ui_pw}"
            encoded_auth = base64.b64encode(auth_string.encode("utf-8")).decode("ascii")
            request.add_header("Authorization", f"Basic {encoded_auth}")

            with urllib.request.urlopen(
                request, timeout=10, context=ssl_context
            ) as response:
                data = json.loads(response.read().decode("utf-8"))
                if "version" in data:
                    logger.info(f"Airflow health check OK. Version: {data['version']}")
                    return {"status": "running", "version": data["version"]}
                logger.warning(
                    "Health check failed: 'version' key not in response JSON."
                )
                return {
                    "status": "unknown",
                    "message": "'version' key missing in response",
                }
        except urllib.error.URLError as e:
            reason = (
                f"HTTP Status: {e.code}"
                if hasattr(e, "code")
                else f"Reason: {e.reason}"
            )
            logger.error(f"Airflow health check failed for {url}. {reason}")
            return {"status": "unknown", "message": f"Connection error: {reason}"}
        except (json.JSONDecodeError, Exception) as e:
            logger.error(
                f"An unexpected error occurred during Airflow health check for {url}: {e}"
            )
            return {"status": "unknown", "message": f"Error: {e}"}

    def get_secrets(self) -> Dict[str, Dict]:
        credentials = {
            key: value
            for key, value in {
                "username": self.ui_user,
                "password": self.ui_pw,
                "port": self.port,
                "secret_key": self.secret_key,
                "secret_path": self.secret_path,
                "base_url": self.service_urls.get("Airflow UI", ""),
            }.items()
            if value
        }
        if not credentials:
            return {}
        return {"airflow_ui_credentials": credentials}
