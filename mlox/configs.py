import os
import logging
import tempfile

from dataclasses import dataclass, field
from abc import abstractmethod, ABC
from typing import Dict, Type, List, Tuple
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
    sys_add_user,
    docker_up,
    docker_down,
    open_ssh_connection,
)

# Configure logging (optional, but recommended)
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)


servers: List | None = None


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
class AbstractService(ABC):
    target_path: str
    target_docker_script: str = field(default="docker-compose.yaml", init=False)
    target_docker_env: str = field(default="service.env", init=False)
    is_running: bool = field(default=False, init=False)
    is_installed: bool = field(default=False, init=False)
    service_url: str = field(default="", init=False)

    @abstractmethod
    def setup(self, conn) -> None:
        pass

    def teardown(self, conn) -> None:
        pass

    def spin_up(self, conn) -> bool:
        docker_up(
            conn,
            f"{self.target_path}/{self.target_docker_script}",
            f"{self.target_path}/{self.target_docker_env}",
        )
        self.is_running = True
        return True

    def spin_down(self, conn) -> bool:
        docker_down(conn, f"{self.target_path}/{self.target_docker_script}")
        self.is_running = False
        return True

    @abstractmethod
    def check(self) -> Dict:
        pass


@dataclass
class ServerConnection:
    credentials: Dict
    _conn: Connection | None = field(default=None, init=False)

    def __init__(self, credentials: Dict):
        self.credentials = credentials

    def __enter__(self):
        try:
            self._conn = open_connection(self.credentials)
            logging.info(f"Successfully opened connection to {self._conn.host}")
            return self._conn
        except Exception as e:
            logging.error(f"Failed to open connection: {e}")
            raise  # Re-raise the exception to be handled by the caller

    def __exit__(self, exc_type, exc_val, exc_tb):
        try:
            if self._conn:
                close_connection(self._conn)
                logging.info(f"Successfully closed connection to {self._conn.host}")
            if exc_type is not None:
                logging.exception(
                    f"An exception occurred during connection usage: {exc_val}"
                )
                # Consider more specific exception handling here based on needs
        except Exception as e:
            logging.error(f"Error during connection cleanup: {e}")
            # Decide whether to re-raise the cleanup exception or let it go (depends on context)


@dataclass
class Server(ABC):
    ip: str
    port: str = field(default="22", init=False)
    root: str
    root_pw: str
    remote_public_key: str
    remote_passphrase: str
    user: str = field(default="mlox", init=False)
    pw: str = field(default_factory=lambda: "me0123", init=False)

    services: List[AbstractService] = field(default_factory=list, init=False)
    setup_complete: bool = field(default=False, init=False)

    def add_service(self, service: AbstractService) -> None:
        self.services.append(service)

    def get_server_connection(self) -> ServerConnection:
        credentials = {
            "host": self.ip,
            "port": self.port,
            "user": self.user,
            "pw": self.pw,
            "passphrase": self.remote_passphrase,
        }
        return ServerConnection(credentials)

    def test_connection(self) -> bool:
        verified = False
        try:
            sc = self.get_server_connection()
            conn = open_connection(sc.credentials)
            close_connection(conn)
            verified = True
            print(f"Public key SSH login verified={verified}.")
        except Exception as e:
            print(f"Failed to login via SSH with public key: {e}")
        return verified

    @abstractmethod
    def setup(self) -> None:
        pass

    @abstractmethod
    def get_server_info(self) -> Tuple[int, float, float]:
        pass


@dataclass
class Ubuntu24Server(Server):
    def update(self):
        with self.get_server_connection() as conn:
            exec_command(conn, "dpkg --configure -a", sudo=True)
            exec_command(conn, "apt-get update", sudo=True)
            exec_command(conn, "apt-get -y upgrade", sudo=True)
            print("Done updating")

    def install_packages(self):
        with self.get_server_connection() as conn:
            exec_command(conn, "dpkg --configure -a", sudo=True)
            exec_command(
                conn, "apt-get -y install mc", sudo=True
            )  # why does it not find mc??
            exec_command(conn, "apt-get -y install git", sudo=True)
            exec_command(conn, "apt-get -y install zsh", sudo=True)

            exec_command(conn, "apt-get -y install ca-certificates curl", sudo=True)
            exec_command(conn, "install -m 0755 -d /etc/apt/keyrings", sudo=True)
            exec_command(
                conn,
                "curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc",
                sudo=True,
            )
            exec_command(conn, "chmod a+r /etc/apt/keyrings/docker.asc", sudo=True)
            exec_command(
                conn,
                'echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | sudo tee /etc/apt/sources.list.d/docker.list',
                sudo=True,
            )
            exec_command(conn, "apt-get update", sudo=True)
            exec_command(
                conn,
                "apt-get -y install docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin",
                sudo=True,
            )

            print("Done updating")

    def get_server_info(self) -> Tuple[int, float, float]:
        cmd = """
                cpu_count=$(lscpu | grep "^CPU(s):" | awk '{print $2}')
                ram_gb=$(free -m | grep Mem | awk '{printf "%.0f", $2/1024}')
                storage_gb=$(df -h / | awk 'NR==2 {print $2}' | sed 's/G//')
                echo "$cpu_count,$ram_gb,$storage_gb" 
            """

        info = None
        with self.get_server_connection() as conn:
            info = exec_command(conn, cmd, sudo=True)
        print(str(info).split(","))
        info = list(map(float, str(info).split(",")))
        return int(info[0]), float(info[1]), float(info[2])

    def setup(self):
        conn = open_ssh_connection(self.ip, self.root, self.root_pw, self.port)

        # 1. add user
        print(f"Add user: {self.user} with password {self.pw}.")
        sys_add_user(conn, self.user, self.pw, with_home_dir=True, sudoer=True)
        close_connection(conn)

        conn = open_ssh_connection(self.ip, self.user, self.pw, self.port)
        # 1. create .ssh dir
        print(f"Create .ssh dir for user {self.user}.")
        command = "mkdir -p ~/.ssh; chmod 700 ~/.ssh"
        exec_command(conn, command)

        # 2. generate rsa keys
        print(f"Generate RSA keys on server {self.ip}.")
        command = f"cd /home/{self.user}/.ssh; rm id_rsa*; ssh-keygen -b 4096 -t rsa -f id_rsa -N mypass"
        exec_command(conn, command, sudo=False)

        # 3. add public key to authorized_keys
        fs_append_line(
            conn, f"/home/{self.user}/.ssh/authorized_keys", self.remote_public_key
        )

        # 4. enable public key login and disable pw auth
        # fs_append_line(
        #     conn, f"/home/{self.user}/.ssh/config", "StrictHostKeyChecking no"
        # )
        # fs_append_line(
        #     conn, f"/home/{self.user}/.ssh/config", "PasswordAuthentication no"
        # )

        # 5. restart ssh server
        # exec_command(conn, "service ssh restart")
        close_connection(conn)

        if not self.test_connection():
            print("Uh oh, something went while setting up the SSH connection. ")
            return

        conn = open_ssh_connection(self.ip, self.root, self.root_pw, self.port)

        fs_find_and_replace(
            conn,
            "/etc/ssh/sshd_config",
            "#PasswordAuthentication yes",
            "PasswordAuthentication no",
        )

        fs_find_and_replace(
            conn,
            "/etc/ssh/sshd_config",
            "X11Forwarding yes",
            "X11Forwarding no",
        )

        fs_find_and_replace(
            conn,
            "/etc/ssh/sshd_config",
            "AllowTcpForwarding yes",
            "AllowTcpForwarding no",
        )
        exec_command(conn, "systemctl restart ssh")
        close_connection(conn)


@dataclass
class Airflow(AbstractService):
    path_dags: str
    path_output: str
    ui_user: str
    ui_pw: str
    port: str
    secret_path: str

    def setup(self, conn) -> None:
        # copy files to target
        fs_create_dir(conn, self.target_path)
        fs_copy(
            conn,
            "./services/airflow/docker-compose-airflow-2.9.2.yaml",
            f"{self.target_path}/{self.target_docker_script}",
        )
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


@dataclass
class MLFlow(AbstractService):
    ui_user: str
    ui_pw: str
    port: str

    def setup(self, conn) -> None:
        fs_create_dir(conn, self.target_path)
        fs_copy(
            conn,
            "./services/tracking/docker-compose-mlflow-traefik.yaml",
            f"{self.target_path}/{self.target_docker_script}",
        )
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

    def check(self) -> Dict:
        return dict()


@dataclass
class OTel(AbstractService):
    relic_endpoint: str
    relic_key: str

    def setup(self, conn) -> None:
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
        tls_setup(conn, conn.host, self.target_path)
        # setup env file
        env_path = f"{self.target_path}/{self.target_docker_env}"
        fs_create_empty_file(conn, env_path)
        fs_append_line(conn, env_path, f"OTEL_RELIC_KEY={self.relic_key}")
        fs_append_line(conn, env_path, f"OTEL_RELIC_ENDPOINT={self.relic_endpoint}")

    def check(self) -> Dict:
        return dict()


@dataclass
class LiteLLM(AbstractService):
    ui_user: str
    ui_pw: str
    port: str
    slack: str
    master_key: str

    def setup(self, conn) -> None:
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
        tls_setup(conn, conn.host, self.target_path)
        base_url = f"https://{conn.host}:{self.port}/ui"
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


@dataclass
class OpenWebUI(AbstractService):
    port: str
    secret_key: str
    litellm_path: str
    litellm_api_key: str
    litellm_base_url: str

    def setup(self, conn) -> None:
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
            f"{conn.host}",
        )

        fs_copy(
            conn,
            # "./services/llm/docker-compose-openwebui-remote.yaml",
            "./services/llm/docker-compose-openwebui-nginx.yaml",
            f"{self.target_path}/{self.target_docker_script}",
        )
        tls_setup(conn, conn.host, self.target_path)
        exec_command(
            conn, f"cp {self.litellm_path}/cert.pem {self.target_path}/litellm.pem"
        )
        base_url = f"https://{conn.host}:{self.port}"
        self.service_url = base_url
        env_path = f"{self.target_path}/{self.target_docker_env}"
        fs_create_empty_file(conn, env_path)
        fs_append_line(conn, env_path, f"OPEN_WEBUI_URL={conn.host}")
        fs_append_line(conn, env_path, f"OPEN_WEBUI_PORT={self.port}")
        fs_append_line(conn, env_path, f"OPEN_WEBUI_SECRET_KEY={self.secret_key}")
        fs_append_line(conn, env_path, f"LITELLM_BASE_URL={self.litellm_base_url}")
        fs_append_line(conn, env_path, f"LITELLM_API_KEY={self.litellm_api_key}")

    def check(self) -> Dict:
        return dict()


@dataclass
class Milvus(AbstractService):
    def setup(self, conn) -> None:
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
        base_url = f"http://{conn.host}:19530"
        self.service_url = base_url
        env_path = f"{self.target_path}/{self.target_docker_env}"
        fs_create_empty_file(conn, env_path)

    def check(self) -> Dict:
        return dict()


@dataclass
class Feast(AbstractService):
    project_name: str

    def setup(self, conn) -> None:
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
        tls_setup(conn, conn.host, self.target_path)

        env_path = f"{self.target_path}/{self.target_docker_env}"
        fs_create_empty_file(conn, env_path)
        fs_append_line(conn, env_path, f"FEAST_PROJECT_NAME={self.project_name}")

    def check(self) -> Dict:
        return dict()


class Infrastructure:
    servers: List[Server]  # = field(default_factory=list, init=False)

    _instance = None  # Class variable to hold the single instance

    def __init__(self):
        self.servers = list()

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = Infrastructure()
        return cls._instance

    def add_server(self, server: Server) -> None:
        self.servers.append(server)

    def get_server_dict(self) -> Dict[str, Server]:
        sd = dict()
        for s in self.servers:
            sd[s.ip] = s
        return sd

    def get_service_by_ip_and_type(
        self, ip: str, t: Type[AbstractService]
    ) -> AbstractService | None:
        server = self.get_server_dict().get(ip, None)
        if server is None:
            return None
        for service in server.services:
            if type(service) is t:
                return service
        return None
