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
import string
import inspect
import logging
import secrets
import textwrap
from importlib import resources
from pathlib import Path
from pathlib import PurePosixPath, PureWindowsPath
from datetime import datetime
from abc import ABC, abstractmethod
from enum import StrEnum
from typing import (
    TYPE_CHECKING,
    Any,
    ClassVar,
    Collection,
    Dict,
    List,
    Literal,
    Mapping,
    Optional,
    Protocol,
)
from dataclasses import dataclass, field, asdict

from mlox.executors import UbuntuTaskExecutor
from mlox.logs import LogSource

# Re-export contracts to preserve existing imports.
from mlox.contracts.services import (
    ServiceCapability,
    AbstractLogService,
    AbstractHealthService,
    AbstractProxyService,
    AbstractWebUIService,
    AbstractObjectStorageService,
    AbstractS3ObjectStorageService,
    AbstractSecretManagerService,
    AbstractSecretManagerBindingService,
    AbstractObservabilityService,
    AbstractMonitorService,
    AbstractTelemetryBindingService,
    AbstractRepositoryService,
    AbstractModelRegistryService,
    AbstractModelServerService,
    AbstractWorkflowOrchestratorService,
)

logger = logging.getLogger(__name__)


def _service_asset_resource(reference: str) -> Path:
    normalized = str(reference).replace("\\", "/")
    relative = PurePosixPath(normalized)
    if (
        relative.is_absolute()
        or PureWindowsPath(reference).is_absolute()
        or not relative.parts
        or ".." in relative.parts
    ):
        raise ValueError(f"Invalid service asset reference: {reference}")
    resource = resources.files("mlox.services").joinpath(*relative.parts)
    if not resource.is_file():
        raise FileNotFoundError(f"Service asset not found: {reference}")
    if not isinstance(resource, Path):
        raise RuntimeError("MLOX service assets must be installed on the filesystem.")
    return resource


def service_asset_path(reference: str) -> Path:
    """Return the local path for a portable packaged asset reference."""

    return _service_asset_resource(reference)


class MloxTemplate(string.Template):
    """Simple service artifact template using ``@variable`` placeholders."""

    delimiter = "@"
    idpattern = r"[_a-zA-Z][_a-zA-Z0-9]*"


if TYPE_CHECKING:
    from mlox.infra import Infrastructure
    from mlox.secret_manager import AbstractSecretManager
    from mlox.object_storage import AbstractObjectStorageClient


SERVICE_HEALTHY_STATUSES = {"running"}
SERVICE_HEALTH_STATUSES = {
    "running",
    "stopped",
    "starting",
    "terminating",
    "failed",
    "error",
    "unknown",
    "un-initialized",
}


def service_health_payload(
    service: Any, probe: Mapping[str, Any] | None
) -> Dict[str, Any]:
    """Return a normalized health payload from a service probe result."""

    payload: Dict[str, Any] = dict(probe or {})
    reported = str(payload.get("status") or "").strip()
    current_state = str(getattr(service, "state", "") or "unknown")
    state = reported if reported in SERVICE_HEALTH_STATUSES else current_state
    if reported in SERVICE_HEALTH_STATUSES:
        try:
            setattr(service, "state", state)
        except Exception:
            pass

    payload["state"] = state
    payload["status"] = reported or state
    payload["healthy"] = payload["status"] in SERVICE_HEALTHY_STATUSES
    return payload


class ServiceLookup(Protocol):
    def get_service_by_uuid(self, service_uuid: str) -> Optional["AbstractService"]: ...

    def get_service_by_name(self, service_name: str) -> Optional["AbstractService"]: ...


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

    # Keep this in sync with ``SERVICE_HEALTH_STATUSES``. Health checks persist
    # their normalized lifecycle result, so transitional and failure states must
    # remain deserializable when a project is reopened.
    state: Literal[
        "un-initialized",
        "starting",
        "running",
        "stopped",
        "terminating",
        "failed",
        "error",
        "unknown",
    ] = field(default="un-initialized", init=False)

    certificate: str = field(default="", init=False)

    exec: UbuntuTaskExecutor = field(default_factory=UbuntuTaskExecutor, init=False)

    def __post_init__(self) -> None:
        # Runtime-only lookup context. Intentionally not a dataclass field so it is
        # excluded from persistence and debug snapshots based on dataclass export.
        self._service_lookup: ServiceLookup | None = None

    def set_task_executor(self, exec: UbuntuTaskExecutor) -> None:
        logger.info(
            f"Setting task executor for service {self.name} supporting {exec.supported_os_ids}"
        )
        self.exec = exec

    def bind_service_lookup(self, lookup: ServiceLookup) -> None:
        self._service_lookup = lookup

    def clear_service_lookup(self) -> None:
        self._service_lookup = None

    def service_dir(self) -> Path:
        """Return the directory containing the concrete service implementation."""

        return Path(inspect.getfile(type(self))).resolve().parent

    def resolve_asset(self, reference: str) -> Path:
        """Resolve a persisted package-relative asset for local filesystem use."""

        return service_asset_path(reference)

    def render_template(self, template_name: str, variables: Mapping[str, Any]) -> str:
        """Render a service-local template with explicit ``@variable`` values.

        Templates are resolved relative to the concrete service implementation
        module, so service artifacts can live next to ``k8s.py``, ``docker.py``,
        and the service ``mlox.*.yaml`` descriptor.
        """

        template_path = self.service_dir() / template_name
        if not template_path.is_file():
            raise FileNotFoundError(f"Template not found: {template_path}")

        template = MloxTemplate(template_path.read_text(encoding="utf-8"))
        try:
            return template.substitute(dict(variables))
        except KeyError as exc:
            missing = exc.args[0]
            raise KeyError(
                f"Missing template variable {missing!r} while rendering "
                f"{template_path}"
            ) from exc
        except ValueError as exc:
            raise ValueError(
                f"Invalid template syntax in {template_path}: {exc}"
            ) from exc

    def render_template_to_file(
        self,
        conn,
        template_name: str,
        remote_path: str,
        variables: Mapping[str, Any],
    ) -> str:
        """Render a service-local template and write it to a remote path."""

        rendered = self.render_template(template_name, variables)
        self.exec.fs_write_file(conn, remote_path, rendered)
        return rendered

    @staticmethod
    def yaml_scalar(value: Any) -> str:
        """Return a safe one-line YAML scalar representation."""

        return json.dumps(value)

    @staticmethod
    def indent_block(value: str, spaces: int) -> str:
        """Indent a multiline block for embedding in YAML block scalars."""

        return textwrap.indent(value.rstrip(), " " * spaces)

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

    def restart(self, conn) -> bool:
        """Repair or restart the service without changing its configuration."""

        if self.compose_service_names and callable(
            getattr(self.exec, "docker_restart", None)
        ):
            return self.compose_restart(conn)
        return self.spin_up(conn)

    def compose_up(self, conn) -> bool:
        """Bring up the docker compose stack for this service."""

        self.exec.docker_up(
            conn,
            f"{self.target_path}/{self.target_docker_script}",
            f"{self.target_path}/{self.target_docker_env}",
        )
        self.state = "running"
        return True

    def compose_restart(self, conn) -> bool:
        """Reconcile the docker compose stack for this service."""

        self.exec.docker_restart(
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
            raise ValueError(f"Unknown service log label: {label}")

        service = self.compose_service_names[label]

        # Use a non-interactive sudo channel and preserve command failures.
        result = conn.sudo(
            "docker ps -a --format '{{.Names}}'", hide=True, warn=True,
            pty=False, in_stream=False, timeout=30,
        )
        if result.exited:
            detail = result.stderr.removeprefix("[sudo] password: ").strip()
            raise RuntimeError(f"Could not list Docker containers (exit {result.exited}): {detail}")
        all_states = result.stdout.splitlines()

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
        raise LookupError(f"Service with label {label} ({service}) not found")

    def log_labels(self) -> List[str]:
        """Return selectable log labels for this service.

        Docker-backed services use their compose labels by default. Kubernetes
        services can override this to expose deployment, pod, or container
        labels without making callers know the backend.
        """

        return list((self.compose_service_names or {}).keys())

    def service_log_tail(self, conn, label: str | None = None, tail: int = 200) -> str:
        """Return recent logs for the selected service log label."""

        labels = self.log_labels()
        chosen_label = label or (labels[0] if labels else None)
        if not chosen_label:
            return "No log labels configured for this service."
        return self.compose_service_log_tail(conn, label=chosen_label, tail=tail)

    def log_tail(self, conn, label: str | None = None, tail: int = 200) -> str:
        if tail < 1:
            raise ValueError("Log tail must be positive.")
        return self.service_log_tail(conn, label=label, tail=tail)

    def get_dependent_service(
        self,
        service_uuid: str,
        *,
        required_type: type[Any] | tuple[type[Any], ...] | None = None,
        required_capabilities: Collection[ServiceCapability | str] = (),
    ) -> Optional["AbstractService"]:
        """Get a compatible dependent service by UUID via the bound lookup."""

        lookup = self._service_lookup
        if lookup is None:
            return None
        service = lookup.get_service_by_uuid(service_uuid)
        if service is None:
            return None
        if required_type is not None and not isinstance(service, required_type):
            return None

        available_capabilities = {
            capability.value if isinstance(capability, ServiceCapability) else str(capability)
            for capability in (getattr(service, "capabilities", set()) or set())
        }
        expected_capabilities = {
            capability.value if isinstance(capability, ServiceCapability) else str(capability)
            for capability in required_capabilities
        }
        if not expected_capabilities.issubset(available_capabilities):
            return None
        return service

    def get_dependent_service_by_name(
        self, service_name: str
    ) -> Optional["AbstractService"]:
        """Get a dependent service by name via the bound service lookup."""

        lookup = self._service_lookup
        if lookup is None:
            return None
        return lookup.get_service_by_name(service_name)

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
