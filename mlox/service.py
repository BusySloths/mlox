"""Service base abstractions and lifecycle contract for deployable MLOX services.

Purpose:
- Provide the common dataclass model and lifecycle methods shared by all concrete services.

Key public classes/functions:
- ``AbstractService`` core base class with setup/spin/check/teardown interfaces
- helper methods for compose execution, dependency lookup, and URL/port registration

Expected runtime mode:
- Remote executor backend used from CLI/UI/TUI workflows

Related modules (plain-text links):
- mlox.infra
- mlox.server
- mlox.executors
- mlox.services
"""

import io
import csv
import json
import uuid
import logging
from abc import ABC, abstractmethod
from typing import Dict, Literal, Optional
from dataclasses import dataclass, field, asdict

from mlox.executors import UbuntuTaskExecutor

logger = logging.getLogger(__name__)


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

    exec: UbuntuTaskExecutor = field(default_factory=UbuntuTaskExecutor, init=False)

    def set_task_executor(self, exec: UbuntuTaskExecutor) -> None:
        logger.info(
            f"Setting task executor for service {self.name} supporting {exec.supported_os_ids}"
        )
        self.exec = exec

    @abstractmethod
    def setup(self, conn) -> None:
        pass

    @abstractmethod
    def teardown(self, conn) -> None:
        pass

    @abstractmethod
    def check(self, conn) -> Dict:
        pass

    @abstractmethod
    def get_secrets(self) -> Dict[str, Dict]:
        """Return a mapping of secret identifiers to structured secret payloads."""
        raise NotImplementedError

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

        self.exec.docker_up(
            conn,
            f"{self.target_path}/{self.target_docker_script}",
            f"{self.target_path}/{self.target_docker_env}",
        )
        self.state = "running"
        return True

    def compose_down(self, conn, *, remove_volumes: bool = False) -> bool:
        """Tear down the docker compose stack for this service."""

        self.exec.docker_down(
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
        all_states = self.exec.docker_all_service_states(conn)

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
                state_val = self.exec.docker_service_state(conn, service)

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
        all_states = self.exec.docker_all_service_states(conn)

        # direct match
        if service in all_states:
            return self.exec.docker_service_log_tails(conn, service, tail=tail)

        # heuristic match
        for cname in all_states:
            if f"_{service}_" in cname:
                return self.exec.docker_service_log_tails(conn, cname, tail=tail)
            if f"-{service}-" in cname:
                return self.exec.docker_service_log_tails(conn, cname, tail=tail)
            elif f"{service}/" in cname:
                return self.exec.docker_service_log_tails(conn, cname, tail=tail)

        # last resort: try service name directly (may be a container id)
        state = self.exec.docker_service_state(conn, service)
        if state:
            return self.exec.docker_service_log_tails(conn, service, tail=tail)

        return f"Service with label {label} ({service}) not found"

    def get_dependent_service(self, service_uuid: str) -> Optional["AbstractService"]:
        """Get a dependent service by UUID using singleton registry."""
        from mlox.service_registry import get_dependent_service

        return get_dependent_service(service_uuid)

    def get_dependent_service_by_name(
        self, service_name: str
    ) -> Optional["AbstractService"]:
        """Get a dependent service by UUID using singleton registry."""
        from mlox.service_registry import get_dependent_service_by_name

        return get_dependent_service_by_name(service_name)

    def dump_state(self, conn) -> None:
        """Persist service debugging artifacts to the target directory."""

        self.exec.fs_create_dir(conn, self.target_path)

        start_script = f"{self.target_path}/start.sh"
        stop_script = f"{self.target_path}/stop.sh"
        env_file = f"{self.target_path}/{self.target_docker_env}"
        self.exec.fs_touch(conn, env_file)
        compose_file = f"{self.target_path}/{self.target_docker_script}"
        start_content = (
            "#!/usr/bin/env bash\n"
            f'docker compose --env-file "{env_file}" -f "{compose_file}" up -d --build\n'
        )
        stop_content = (
            "#!/usr/bin/env bash\n"
            f'docker compose --env-file "{env_file}" -f "{compose_file}" down --remove-orphans\n'
        )
        self.exec.fs_write_file(conn, start_script, start_content)
        self.exec.fs_write_file(conn, stop_script, stop_content)
        self.exec.fs_set_permissions(conn, start_script, "750")
        self.exec.fs_set_permissions(conn, stop_script, "750")

        history = list(self.exec.history)
        fieldnames = sorted({key for entry in history for key in entry.keys()}) or [
            "timestamp",
            "action",
            "status",
        ]
        buffer = io.StringIO()
        writer = csv.DictWriter(buffer, fieldnames=fieldnames)
        writer.writeheader()
        for entry in history:
            writer.writerow({field: entry.get(field, "") for field in fieldnames})
        history_path = f"{self.target_path}/exec_history.csv"
        self.exec.fs_write_file(conn, history_path, buffer.getvalue())

        service_dict = asdict(self)
        service_json = json.dumps(service_dict, indent=2, sort_keys=True, default=str)
        service_json_path = f"{self.target_path}/service-state.json"
        self.exec.fs_write_file(conn, service_json_path, service_json)
