from mlox.remote import docker_down, docker_up


from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Dict

from mlox.remote import exec_command, fs_copy, fs_create_dir, fs_find_and_replace


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
    target_path: str
    target_docker_script: str = field(default="docker-compose.yaml", init=False)
    target_docker_env: str = field(default="service.env", init=False)

    service_url: str = field(default="", init=False)
    service_ports: Dict[str, int] = field(default_factory=dict, init=False)

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
        return True

    def spin_down(self, conn) -> bool:
        docker_down(conn, f"{self.target_path}/{self.target_docker_script}")
        return True

    @abstractmethod
    def check(self) -> Dict:
        pass
