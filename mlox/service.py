import uuid

from typing import Dict, Literal
from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from mlox.remote import (
    docker_down,
    docker_service_state,
    docker_all_service_states,
    docker_up,
    docker_service_log_tails,
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
    cmd = (
        f"cd {path}; "
        "openssl x509 -req -in server.csr -signkey key.pem "
        "-out cert.pem -days 365 -extensions req_ext -extfile openssl-san.cnf"
    )
    exec_command(conn, cmd)
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

        # Prefer to gather container state via docker inspect helper which is
        # generally more reliable than parsing `docker compose ps` output and
        # avoids running compose in environments where it's not available.
        all_states = docker_all_service_states(conn)

        results: Dict[str, str] = {}
        for label, service in self.compose_service_names.items():
            state_val: str | None = None

            # Direct match: the compose service may already be the container name
            if service in all_states:
                s = all_states[service]
                if isinstance(s, dict):
                    state_val = s.get("Status") or s.get("State") or None

            # Heuristic: container names created by compose often contain the
            # service name as part of '<project>_<service>_<replica>'. Try to
            # find a container name that contains the compose service name.
            if state_val is None and all_states:
                for cname, sdict in all_states.items():
                    if f"_{service}_" in cname or cname.endswith(f"_{service}_1"):
                        if isinstance(sdict, dict):
                            state_val = (
                                sdict.get("Status") or sdict.get("State") or None
                            )
                            break

            # Last-resort: ask Docker for the state of the named service/container
            if not state_val:
                state_val = docker_service_state(conn, service)

            results[label] = state_val or "unknown"
        return results

    def compose_service_log_tail(self, conn, label: str, tail: int = 200) -> str:
        """Return the recent log tail for a tracked compose service label.

        Resolves the compose service name to a container name using the same
        heuristics as `compose_service_status` and then returns the last
        `tail` lines using the remote helper.
        """
        if label not in self.compose_service_names:
            return "Not found"

        service = self.compose_service_names[label]

        # Try to resolve container name from current docker state
        all_states = docker_all_service_states(conn)

        # direct match
        if service in all_states:
            return docker_service_log_tails(conn, service, tail=tail)

        # heuristic match
        for cname in all_states:
            if f"_{service}_" in cname or cname.endswith(f"_{service}_1"):
                return docker_service_log_tails(conn, cname, tail=tail)
            elif f"{service}/" in cname:
                return docker_service_log_tails(conn, cname, tail=tail)

        # last resort: try service name directly (may be a container id)
        state = docker_service_state(conn, service)
        if state:
            return docker_service_log_tails(conn, service, tail=tail)

        return f"Service with label {label} ({service}) not found"
