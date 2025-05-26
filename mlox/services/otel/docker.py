import logging

from dataclasses import dataclass, field
from typing import Dict

from mlox.service import AbstractService, tls_setup
from mlox.remote import (
    fs_copy,
    fs_read_file,
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
class OtelDockerService(AbstractService):
    relic_endpoint: str
    relic_key: str
    config: str
    certificate: str = field(default="", init=False)

    def setup(self, conn) -> None:
        fs_create_dir(conn, self.target_path)
        fs_copy(conn, self.template, f"{self.target_path}/{self.target_docker_script}")
        fs_copy(conn, self.config, f"{self.target_path}/otel-collector-config.yaml")
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
        self.certificate = fs_read_file(
            conn, f"{self.target_path}/cert.pem", format="txt/plain"
        )
        # setup env file
        env_path = f"{self.target_path}/{self.target_docker_env}"
        fs_create_empty_file(conn, env_path)
        fs_append_line(conn, env_path, f"OTEL_RELIC_KEY={self.relic_key}")
        fs_append_line(conn, env_path, f"OTEL_RELIC_ENDPOINT={self.relic_endpoint}")
        self.service_url = f"https://{conn.host}:13133/"
        self.service_ports["OTLP gRPC receiver"] = 4317
        self.service_ports["OTLP HTTP receiver"] = 4318
        self.service_ports["OTEL health check"] = 13133

    def check(self, conn) -> Dict:
        return dict()
