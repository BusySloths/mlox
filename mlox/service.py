from typing import Dict, Literal
from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from mlox.remote import (
    docker_down,
    docker_up,
    exec_command,
    fs_copy,
    fs_create_dir,
    fs_find_and_replace,
)


def tls_setup_no_config(conn, ip, path) -> None:
    # copy files to target
    fs_create_dir(conn, path)

    # Define the subject for the certificate.
    # For a basic self-signed cert, CN (Common Name) is usually the hostname or IP.
    # You can add more fields like /C=US/ST=California/L=City/O=Organization/OU=OrgUnit
    # Ensure 'ip' is properly escaped if it contains special characters, though unlikely for an IP.
    subject = f"/CN={ip}"

    # certificates
    exec_command(conn, f"cd {path}; openssl genrsa -out key.pem 2048")
    # Generate CSR non-interactively using the -subj argument
    exec_command(
        conn,
        f"cd {path}; openssl req -new -key key.pem -out server.csr -subj '{subject}'",
    )
    # Generate self-signed certificate from CSR
    exec_command(
        conn,
        f"cd {path}; openssl x509 -req -in server.csr -signkey key.pem -out cert.pem -days 365",
    )
    exec_command(conn, f"chmod u=rw,g=rw,o=rw {path}/key.pem")
    exec_command(conn, f"chmod u=rw,g=rw,o=rw {path}/cert.pem")


def tls_setup(conn, ip, path) -> None:
    # copy files to target
    fs_create_dir(conn, path)
    fs_copy(conn, "./stacks/mlox/openssl-san.cnf", f"{path}/openssl-san.cnf")
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
    name: str
    template: str
    target_path: str
    target_docker_script: str = field(default="docker-compose.yaml", init=False)
    target_docker_env: str = field(default="service.env", init=False)

    service_urls: Dict[str, str] = field(default_factory=dict, init=False)
    service_ports: Dict[str, int] = field(default_factory=dict, init=False)

    state: Literal["un-initialized", "running", "stopped", "unknown"] = field(
        default="un-initialized", init=False
    )

    certificate: str = field(default="", init=False)

    @abstractmethod
    def setup(self, conn) -> None:
        pass

    @abstractmethod
    def teardown(self, conn) -> None:
        pass

    @abstractmethod
    def check(self, conn) -> Dict:
        pass

    def spin_up(self, conn) -> bool:
        docker_up(
            conn,
            f"{self.target_path}/{self.target_docker_script}",
            f"{self.target_path}/{self.target_docker_env}",
        )
        return True

    def spin_down(self, conn) -> bool:
        docker_down(conn, f"{self.target_path}/{self.target_docker_script}")
        return True
