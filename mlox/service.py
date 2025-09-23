import json
import logging
import uuid

from typing import Dict, Literal
from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from mlox.remote import (
    docker_down,
    docker_service_state,
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
    compose_service_names: Dict[str, str] = field(default_factory=dict, init=False)

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
        """Start the service.

        Concrete services should override this method to perform any
        provisioning logic required to run the service. The default
        implementation exists solely to satisfy type checkers and unit tests
        that rely on instantiating ``AbstractService`` subclasses without
        providing spin control behavior.
        """

        raise NotImplementedError("spin_up must be implemented by subclasses")

    def spin_down(self, conn) -> bool:
        """Stop the service."""

        raise NotImplementedError("spin_down must be implemented by subclasses")

    def compose_up(self, conn) -> bool:
        """Bring up the docker compose stack for this service."""

        docker_up(
            conn,
            f"{self.target_path}/{self.target_docker_script}",
            f"{self.target_path}/{self.target_docker_env}",
        )
        self.state = "running"
        return True

    def compose_down(self, conn, *, remove_volumes: bool = False) -> bool:
        """Tear down the docker compose stack for this service."""

        docker_down(
            conn,
            f"{self.target_path}/{self.target_docker_script}",
            remove_volumes=remove_volumes,
        )
        self.state = "stopped"
        return True

    def compose_service_status(self, conn) -> Dict[str, str]:
        """Return docker compose state for tracked services.

        Attempts to use ``docker compose ps`` to retrieve structured service state
        information. Falls back to inspecting individual containers when the
        structured output is unavailable.
        """

        compose_file = f"{self.target_path}/{self.target_docker_script}"
        service_states: Dict[str, str] = {}

        try:
            output = exec_command(
                conn,
                f'docker compose -f "{compose_file}" ps --format json',
                sudo=True,
                pty=False,
            )
            if output:
                parsed = json.loads(output)
                for entry in parsed:
                    service = entry.get("Service")
                    state = entry.get("State") or entry.get("Status")
                    if service:
                        service_states[service] = state or "unknown"
        except Exception as exc:  # pragma: no cover - defensive logging
            logging.debug("Failed to read compose service states: %s", exc)

        results: Dict[str, str] = {}
        for label, service in self.compose_service_names.items():
            state = service_states.get(service)
            if not state:
                state = docker_service_state(conn, service)
            results[label] = state or "unknown"
        return results
