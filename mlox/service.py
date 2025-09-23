import uuid

from importlib import resources
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


def get_stacks_path() -> str:
    # return str(resources.files("mlox.stacks.mlox"))
    return "./mlox/stacks/mlox"


def tls_setup(conn, ip, path) -> None:
    # copy files to target
    fs_create_dir(conn, path)

    stacks_path = get_stacks_path()
    fs_copy(conn, f"{stacks_path}/openssl-san.cnf", f"{path}/openssl-san.cnf")
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
    service_config_id: str
    template: str
    target_path: str
    uuid: str = field(default_factory=lambda: uuid.uuid4().hex, init=False)

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
        self.state = "running"
        return True

    def spin_down(self, conn) -> bool:
        docker_down(conn, f"{self.target_path}/{self.target_docker_script}")
        self.state = "stopped"
        return True


# SKETCH of a mixin for Docker services
# This mixin can be used to provide common Docker functionality to services
# that need to run in Docker containers, such as Airflow or MLFlow.
# @dataclass
# class DockerMixin:
#     target_docker_script: str = field(default="docker-compose.yaml", init=False)
#     target_docker_env: str = field(default="service.env", init=False)

#     def spin_up(self, conn, target_path: str) -> bool:
#         docker_up(
#             conn,
#             f"{target_path}/{self.target_docker_script}",
#             f"{target_path}/{self.target_docker_env}",
#         )
#         self.state = "running"
#         return True

#     def spin_down(self, conn, target_path: str) -> bool:
#         docker_down(conn, f"{target_path}/{self.target_docker_script}")
#         self.state = "stopped"
#         return True

# SKETCH 2 of a mixin for Docker services using Protocols
# from typing import Protocol, TypeVar, runtime_checkable


# @runtime_checkable
# class DockerServiceLike(Protocol):
#     target_path: str
#     target_docker_script: str
#     target_docker_env: str
#     compose_service_names: Dict[str, str]
#     state: str


# T = TypeVar("T", bound=DockerServiceLike)


# class ServiceDockerMixin:
#     """
#     Lightweight mixin that expects the concrete class to provide the
#     attributes defined in DockerServiceLike. Use static typing to ensure
#     the concrete class implements the protocol.
#     """

#     def spin_up(self: T, conn) -> bool:

#     def spin_down(self: T, conn) -> bool:

#     def check_services(self: T, conn) -> Dict:

#     def get_logs(self: T, conn) -> Dict:
