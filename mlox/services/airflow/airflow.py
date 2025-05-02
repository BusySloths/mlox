import logging

from dataclasses import dataclass, field
from typing import Dict

from mlox.configs import AbstractService, tls_setup
from mlox.remote import (
    fs_copy,
    fs_create_dir,
    fs_create_empty_file,
    fs_append_line,
    sys_user_id,
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
    secret_path: str
    template: str

    def __str__(self):
        return f"AirflowDockerService(path_dags={self.path_dags}, path_output={self.path_output}, ui_user={self.ui_user}, ui_pw={self.ui_pw}, port={self.port}, secret_path={self.secret_path})"

    def setup(self, conn) -> None:
        # copy files to target
        fs_create_dir(conn, self.target_path)
        fs_copy(conn, self.template, f"{self.target_path}/{self.target_docker_script}")
        tls_setup(conn, conn.host, self.target_path)
        # fs_copy(
        #     conn,
        #     "./services/generate_selfsigned_ssl_certs.sh",
        #     f"{self.target_path}/generate.sh",
        # )
        # # setup certificates
        # fs_find_and_replace(
        #     conn, f"{self.target_path}/generate.sh", "cert.pem", "airflow.crt"
        # )
        # fs_find_and_replace(
        #     conn, f"{self.target_path}/generate.sh", "key.pem", "airflow.key"
        # )
        # exec_command(conn, f"cd {self.target_path}; ./generate.sh")
        # setup environment
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
        self.is_installed = True

    def check(self) -> Dict:
        return dict()
