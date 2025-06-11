import logging

from dataclasses import dataclass
from typing import Dict

from mlox.service import AbstractService, tls_setup
from mlox.remote import (
    fs_copy,
    fs_delete_dir,
    fs_create_dir,
    fs_create_empty_file,
    fs_append_line,
    sys_user_id,
    docker_down,
)

# Configure logging (optional, but recommended)
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)


@dataclass
class AirflowDockerService(AbstractService):
    path_dags: str
    path_output: str
    ui_user: str
    ui_pw: str
    port: str
    secret_path: str = ""

    def __str__(self):
        return f"AirflowDockerService(path_dags={self.path_dags}, path_output={self.path_output}, ui_user={self.ui_user}, ui_pw={self.ui_pw}, port={self.port}, secret_path={self.secret_path})"

    def setup(self, conn) -> None:
        # copy files to target
        fs_create_dir(conn, self.target_path)
        # Ensure host directories for DAGs and logs/outputs exist and are owned by mlox_user
        # This is crucial for volume mounts to have correct permissions for AIRFLOW_UID.
        fs_create_dir(conn, self.path_dags)
        fs_create_dir(conn, self.path_output)
        # fs_create_dir(conn, self.target_path + "/logs")
        # fs_create_dir(conn, self.target_path + "/plugins")

        fs_copy(conn, self.template, f"{self.target_path}/{self.target_docker_script}")
        tls_setup(conn, conn.host, self.target_path)
        # setup environment
        base_url = f"https://{conn.host}:{self.port}"
        if len(self.secret_path) >= 1:
            base_url = f"https://{conn.host}:{self.port}/{self.secret_path}"
        self.service_url = base_url
        env_path = f"{self.target_path}/{self.target_docker_env}"
        fs_create_empty_file(conn, env_path)
        fs_append_line(conn, env_path, "_AIRFLOW_SSL_CERT_NAME=cert.pem")
        fs_append_line(conn, env_path, "_AIRFLOW_SSL_KEY_NAME=key.pem")
        fs_append_line(conn, env_path, f"AIRFLOW_UID={sys_user_id(conn)}")
        fs_append_line(conn, env_path, f"_AIRFLOW_SSL_FILE_PATH={self.target_path}/")
        fs_append_line(conn, env_path, f"_AIRFLOW_OUT_PORT={self.port}")
        fs_append_line(conn, env_path, f"_AIRFLOW_BASE_URL={base_url}")
        fs_append_line(conn, env_path, f"_AIRFLOW_WWW_USER_USERNAME={self.ui_user}")
        fs_append_line(conn, env_path, f"_AIRFLOW_WWW_USER_PASSWORD={self.ui_pw}")
        fs_append_line(conn, env_path, f"_AIRFLOW_OUT_FILE_PATH={self.path_output}")
        fs_append_line(conn, env_path, f"_AIRFLOW_DAGS_FILE_PATH={self.path_dags}")
        fs_append_line(conn, env_path, "_AIRFLOW_LOAD_EXAMPLES=false")
        self.service_ports["Airflow Webserver"] = int(self.port)

    def teardown(self, conn):
        docker_down(
            conn,
            f"{self.target_path}/{self.target_docker_script}",
            remove_volumes=True,
        )
        fs_delete_dir(conn, self.target_path)

    def check(self, conn) -> Dict:
        return dict()
