import os
import tempfile

from dataclasses import dataclass, field
from abc import abstractmethod, ABC
from typing import Dict, Type
from fabric import Connection  # type: ignore

from mlox.remote import (
    get_config,
    open_connection,
    close_connection,
    exec_command,
    fs_copy,
    fs_create_dir,
    fs_find_and_replace,
    fs_create_empty_file,
    fs_append_line,
    sys_user_id,
    docker_up,
    docker_down,
)

services: Dict | None = None


def tls_setup(conn, ip, path) -> None:
    # copy files to target
    fs_create_dir(conn, path)
    fs_copy(conn, "./services/monitor/openssl-san.cnf", f"{path}/openssl-san.cnf")
    fs_find_and_replace(conn, f"{path}/openssl-san.cnf", "<MY_IP>", f"{ip}")
    # certificates
    exec_command(conn, f"cd {path}; openssl genrsa -out key.pem 2048")
    exec_command(
        conn,
        f"cd {path}; openssl req -new -key key.pem -out server.csr -config openssl-san.cnf",
    )
    exec_command(
        conn,
        f"cd {path}; openssl x509 -req -in server.csr -signkey key.pem -out cert.pem -days 365 -extensions req_ext -extfile openssl-san.cnf",
    )
    exec_command(conn, f"chmod u=rw,g=rw,o=rw {path}/key.pem")


@dataclass
class ServerConnection:
    ip: str
    user: str
    credentials: Dict
    _tmp_dir: tempfile.TemporaryDirectory | None = field(default=None, init=False)
    _conn: Connection | None = field(default=None, init=False)

    def __enter__(self):
        self._conn, self._tmp_dir = open_connection(self.credentials)
        return self._conn

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type is not None:
            print(exc_type, exc_val, exc_tb)
            raise Exception()
        close_connection(self._conn, self._tmp_dir)


@dataclass
class AbstractService(ABC):
    server: ServerConnection
    target_path: str
    target_docker_script: str = field(default="docker-compose.yaml", init=False)
    target_docker_env: str = field(default="service.env", init=False)

    @abstractmethod
    def setup(self) -> None:
        pass

    def spin_up(self) -> bool:
        with self.server as conn:
            docker_up(
                conn,
                f"{self.target_path}/{self.target_docker_script}",
                f"{self.target_path}/{self.target_docker_env}",
            )
        return True

    def spin_down(self) -> bool:
        with self.server as conn:
            docker_down(conn, f"{self.target_path}/{self.target_docker_script}")
        return True

    @abstractmethod
    def check(self) -> Dict:
        pass

    @abstractmethod
    def get_service_url(self) -> str:
        pass


@dataclass
class Airflow(AbstractService):
    path_dags: str
    path_output: str
    ui_user: str
    ui_pw: str
    port: str
    secret_path: str

    def setup(self) -> None:
        with self.server as conn:
            # copy files to target
            fs_create_dir(conn, self.target_path)
            fs_copy(
                conn,
                "./services/airflow/docker-compose-airflow-2.9.2.yaml",
                f"{self.target_path}/{self.target_docker_script}",
            )
            tls_setup(conn, self.server.ip, self.target_path)
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
            base_url = f"https://{self.server.ip}:{self.port}/{self.secret_path}"
            self.service_url = base_url
            env_path = f"{self.target_path}/{self.target_docker_env}"
            fs_create_empty_file(conn, env_path)
            fs_append_line(conn, env_path, "_AIRFLOW_SSL_CERT_NAME=cert.pem")
            fs_append_line(conn, env_path, "_AIRFLOW_SSL_KEY_NAME=key.pem")
            fs_append_line(conn, env_path, f"AIRFLOW_UID={sys_user_id(conn)}")
            fs_append_line(
                conn, env_path, f"_AIRFLOW_SSL_FILE_PATH={self.target_path}/"
            )
            fs_append_line(conn, env_path, f"_AIRFLOW_OUT_PORT={self.port}")
            fs_append_line(conn, env_path, f"_AIRFLOW_BASE_URL={base_url}")
            fs_append_line(conn, env_path, f"_AIRFLOW_WWW_USER_USERNAME={self.ui_user}")
            fs_append_line(conn, env_path, f"_AIRFLOW_WWW_USER_PASSWORD={self.ui_pw}")
            fs_append_line(conn, env_path, f"_AIRFLOW_OUT_FILE_PATH={self.path_output}")
            fs_append_line(conn, env_path, f"_AIRFLOW_DAGS_FILE_PATH={self.path_dags}")
            fs_append_line(conn, env_path, "_AIRFLOW_LOAD_EXAMPLES=false")

    def check(self) -> Dict:
        return dict()

    def get_service_url(self) -> str:
        return f"https://{self.server.ip}:{self.port}/{self.secret_path}"


@dataclass
class MLFlow(AbstractService):
    ui_user: str
    ui_pw: str
    port: str

    def setup(self) -> None:
        with self.server as conn:
            fs_create_dir(conn, self.target_path)
            fs_copy(
                conn,
                "./services/tracking/docker-compose-mlflow-traefik.yaml",
                f"{self.target_path}/{self.target_docker_script}",
            )
            env_path = f"{self.target_path}/{self.target_docker_env}"
            fs_create_empty_file(conn, env_path)
            fs_append_line(conn, env_path, f"MLFLOW_PORT={self.port}")
            fs_append_line(conn, env_path, f"MLFLOW_URL={self.server.ip}")
            fs_append_line(conn, env_path, f"MLFLOW_USERNAME={self.ui_user}")
            fs_append_line(conn, env_path, f"MLFLOW_PASSWORD={self.ui_pw}")

    def check(self) -> Dict:
        return dict()

    def get_service_url(self) -> str:
        return f"https://{self.server.ip}:{self.port}"


@dataclass
class OTel(AbstractService):
    relic_endpoint: str
    relic_key: str

    def setup(self) -> None:
        with self.server as conn:
            fs_create_dir(conn, self.target_path)
            fs_copy(
                conn,
                "./services/monitor/docker-compose-otel.yaml",
                f"{self.target_path}/{self.target_docker_script}",
            )
            fs_copy(
                conn,
                "./services/monitor/otel-collector-config-remote.yaml",
                f"{self.target_path}/otel-collector-config.yaml",
            )
            # fs_copy(
            #     conn,
            #     "./services/monitor/openssl-san.cnf",
            #     f"{self.target_path}/openssl-san.cnf",
            # )
            # fs_find_and_replace(
            #     conn,
            #     f"{self.target_path}/openssl-san.cnf",
            #     "<MY_IP>",
            #     f"{self.server.ip}",
            # )
            # # certificates
            # exec_command(
            #     conn,
            #     f"cd {self.target_path}; openssl genrsa -out key.pem 2048",
            # )
            # exec_command(
            #     conn,
            #     f"cd {self.target_path}; openssl req -new -key key.pem -out server.csr -config openssl-san.cnf",
            # )
            # exec_command(
            #     conn,
            #     f"cd {self.target_path}; openssl x509 -req -in server.csr -signkey key.pem -out cert.pem -days 365 -extensions req_ext -extfile openssl-san.cnf",
            # )
            # exec_command(conn, f"chmod u=rw,g=rw,o=rw {self.target_path}/key.pem")
            tls_setup(conn, self.server.ip, self.target_path)
            # setup env file
            env_path = f"{self.target_path}/{self.target_docker_env}"
            fs_create_empty_file(conn, env_path)
            fs_append_line(conn, env_path, f"OTEL_RELIC_KEY={self.relic_key}")
            fs_append_line(conn, env_path, f"OTEL_RELIC_ENDPOINT={self.relic_endpoint}")

    def check(self) -> Dict:
        return dict()

    def get_service_url(self) -> str:
        return f"https://{self.server.ip}:13133/health/status"


@dataclass
class LiteLLM(AbstractService):
    ui_user: str
    ui_pw: str
    port: str
    slack: str
    master_key: str

    def setup(self) -> None:
        with self.server as conn:
            # copy files to target
            fs_create_dir(conn, self.target_path)
            fs_copy(
                conn,
                "./services/llm/entrypoint.sh",
                f"{self.target_path}/entrypoint.sh",
            )
            fs_copy(
                conn,
                "./services/llm/litellm-config.yaml",
                f"{self.target_path}/litellm-config.yaml",
            )
            fs_copy(
                conn,
                "./services/llm/docker-compose-litellm-remote.yaml",
                f"{self.target_path}/{self.target_docker_script}",
            )
            tls_setup(conn, self.server.ip, self.target_path)
            base_url = f"https://{self.server.ip}:{self.port}/ui"
            self.service_url = base_url
            env_path = f"{self.target_path}/{self.target_docker_env}"
            fs_create_empty_file(conn, env_path)
            fs_append_line(conn, env_path, f"MY_LITELLM_MASTER_KEY={self.master_key}")
            fs_append_line(conn, env_path, f"MY_LITELLM_SLACK_WEBHOOK={self.slack}")
            fs_append_line(conn, env_path, f"MY_LITELLM_PORT={self.port}")
            fs_append_line(conn, env_path, f"MY_LITELLM_USERNAME={self.ui_user}")
            fs_append_line(conn, env_path, f"MY_LITELLM_PASSWORD={self.ui_pw}")

    def check(self) -> Dict:
        return dict()

    def get_service_url(self) -> str:
        return f"https://{self.server.ip}:{self.port}/ui"


@dataclass
class OpenWebUI(AbstractService):
    port: str
    secret_key: str
    litellm_path: str
    litellm_api_key: str
    litellm_base_url: str

    def setup(self) -> None:
        with self.server as conn:
            # copy files to target
            fs_create_dir(conn, self.target_path)
            fs_copy(
                conn,
                "./services/llm/open-webui.conf",
                f"{self.target_path}/open-webui.conf",
            )
            fs_find_and_replace(
                conn,
                f"{self.target_path}/open-webui.conf",
                "your_domain_or_IP",
                f"{self.server.ip}",
            )

            fs_copy(
                conn,
                # "./services/llm/docker-compose-openwebui-remote.yaml",
                "./services/llm/docker-compose-openwebui-nginx.yaml",
                f"{self.target_path}/{self.target_docker_script}",
            )
            tls_setup(conn, self.server.ip, self.target_path)
            exec_command(
                conn, f"cp {self.litellm_path}/cert.pem {self.target_path}/litellm.pem"
            )
            base_url = f"https://{self.server.ip}:{self.port}"
            self.service_url = base_url
            env_path = f"{self.target_path}/{self.target_docker_env}"
            fs_create_empty_file(conn, env_path)
            fs_append_line(conn, env_path, f"OPEN_WEBUI_URL={self.server.ip}")
            fs_append_line(conn, env_path, f"OPEN_WEBUI_PORT={self.port}")
            fs_append_line(conn, env_path, f"OPEN_WEBUI_SECRET_KEY={self.secret_key}")
            fs_append_line(conn, env_path, f"LITELLM_BASE_URL={self.litellm_base_url}")
            fs_append_line(conn, env_path, f"LITELLM_API_KEY={self.litellm_api_key}")

    def check(self) -> Dict:
        return dict()

    def get_service_url(self) -> str:
        return f"https://{self.server.ip}:{self.port}"


@dataclass
class Milvus(AbstractService):
    def setup(self) -> None:
        with self.server as conn:
            # copy files to target
            fs_create_dir(conn, self.target_path)
            fs_copy(
                conn,
                "./services/llm/docker-compose-milvus.yaml",
                f"{self.target_path}/{self.target_docker_script}",
            )
            # exec_command(
            #     conn,
            #     f"htpasswd -b -c {self.target_path}/htpasswd {self.user_name} {self.user_pass}",
            # )
            base_url = f"http://{self.server.ip}:19530"
            self.service_url = base_url
            env_path = f"{self.target_path}/{self.target_docker_env}"
            fs_create_empty_file(conn, env_path)

    def check(self) -> Dict:
        return dict()

    def get_service_url(self) -> str:
        return f"http://{self.server.ip}:19530"


@dataclass
class Feast(AbstractService):
    project_name: str

    def setup(self) -> None:
        with self.server as conn:
            # copy files to target
            fs_create_dir(conn, self.target_path)
            fs_copy(
                conn,
                "./services/features/feature_store.yaml",
                f"{self.target_path}/feature_store.yaml",
            )
            fs_find_and_replace(
                conn,
                f"{self.target_path}/feature_store.yaml",
                "my_project",
                f"{self.project_name}",
            )
            fs_copy(
                conn,
                "./services/features/Dockerfile",
                f"{self.target_path}/Dockerfile",
            )
            fs_copy(
                conn,
                "./services/features/docker-compose-feast.yaml",
                f"{self.target_path}/{self.target_docker_script}",
            )
            tls_setup(conn, self.server.ip, self.target_path)

            env_path = f"{self.target_path}/{self.target_docker_env}"
            fs_create_empty_file(conn, env_path)
            fs_append_line(conn, env_path, f"FEAST_PROJECT_NAME={self.project_name}")

    def check(self) -> Dict:
        return dict()

    def get_service_url(self) -> str:
        return f"http://{self.server.ip}:8080"


def get_servers() -> Dict[str, ServerConnection]:
    ip1 = os.environ.get("SERVER_01", "")
    user1 = os.environ.get("USER_01", "")
    sc1 = ServerConnection(
        ip1, user1, get_config(ip1, os.environ.get("SYS_USER_PW", ""))
    )
    return {ip1: sc1}


def update_service(service) -> Dict:
    global services
    if services is None:
        services = dict()
    services[(service.server.ip, type(service))] = service
    return services


def get_service_by_ip_and_type(
    ip: str, t: Type[AbstractService]
) -> AbstractService | None:
    global services
    if services is None:
        services = dict()
    return services.get((ip, t), None)
