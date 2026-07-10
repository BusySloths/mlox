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
import textwrap
from pathlib import Path
from datetime import datetime
from abc import ABC, abstractmethod
from enum import StrEnum
from typing import (
    TYPE_CHECKING,
    Any,
    ClassVar,
    Dict,
    List,
    Literal,
    Mapping,
    Optional,
    Protocol,
)
from dataclasses import dataclass, field, asdict

from mlox.executors import UbuntuTaskExecutor

logger = logging.getLogger(__name__)


class MloxTemplate(string.Template):
    """Simple service artifact template using ``@variable`` placeholders."""

    delimiter = "@"
    idpattern = r"[_a-zA-Z][_a-zA-Z0-9]*"


if TYPE_CHECKING:
    from mlox.infra import Infrastructure
    from mlox.secret_manager import AbstractSecretManager


class ServiceCapability(StrEnum):
    """User-facing service capabilities advertised by service configs/classes."""

    WEB_UI = "web_ui"
    SECRET_MANAGER = "secret_manager"
    REPOSITORY = "repository"
    MODEL_REGISTRY = "model_registry"
    MODEL_SERVER = "model_server"
    MONITOR = "monitor"
    OBSERVABILITY = "observability"
    DATA_WAREHOUSE = "data_warehouse"
    OBJECT_STORAGE = "object_storage"
    SPREADSHEET = "spreadsheet"
    DATABASE = "database"
    VECTOR_DATABASE = "vector_database"
    CACHE = "cache"
    MESSAGE_BROKER = "message_broker"
    WORKFLOW_ORCHESTRATOR = "workflow_orchestrator"
    FEATURE_STORE = "feature_store"
    CONTAINER_REGISTRY = "container_registry"
    DEPLOYMENT = "deployment"
    LLM = "llm"
    DASHBOARD = "dashboard"
    DEVELOPER_TOOLS = "developer_tools"


class AbstractSecretManagerService(ABC):
    """Service capability mixin for services that provide a secret manager client."""

    capabilities: ClassVar[set[ServiceCapability]] = {ServiceCapability.SECRET_MANAGER}

    @abstractmethod
    def get_secret_manager(
        self, infra: "Infrastructure"
    ) -> "AbstractSecretManager":
        """Return an AbstractSecretManager client for this service."""
        pass


class AbstractWebUIService(ABC):
    """Service capability mixin for services with a browser-facing UI."""

    capabilities: ClassVar[set[ServiceCapability]] = {ServiceCapability.WEB_UI}
    web_ui_url_label: ClassVar[str | None] = None
    web_ui_login_fields: ClassVar[tuple[str, ...]] = ()

    def get_web_ui_address(self) -> str:
        """Return the preferred browser URL for this service, if available."""

        urls = getattr(self, "service_urls", {}) or {}
        if self.web_ui_url_label:
            url = urls.get(self.web_ui_url_label)
            if url:
                return str(url)

        for label, url in urls.items():
            label_text = str(label).lower()
            if any(
                term in label_text
                for term in ("ui", "dashboard", "console", "login")
            ):
                return str(url)

        url = getattr(self, "service_url", "")
        return str(url or "")

    def get_web_ui_login(self, bundle: Any | None = None) -> dict[str, str]:
        """Return browser-login credentials for this service, if available."""

        credentials: dict[str, str] = {}
        username = getattr(self, "ui_user", None) or getattr(self, "root_user", None)
        password = getattr(self, "ui_pw", None) or getattr(self, "root_password", None)
        if username:
            credentials["username"] = str(username)
        if password:
            credentials["password"] = str(password)
        return credentials


@dataclass
class AbstractRepositoryService(ABC):
    """Service capability mixin for repository provider services."""

    capabilities: ClassVar[set[ServiceCapability]] = {ServiceCapability.REPOSITORY}
    repo_name: str = field(default="", init=False)
    created_timestamp: str = field(default_factory=datetime.now().isoformat, init=False)
    modified_timestamp: str = field(default_factory=datetime.now().isoformat, init=False)

    @abstractmethod
    def get_url(self) -> str:
        pass

    @abstractmethod
    def git_clone(self, conn) -> None:
        pass

    @abstractmethod
    def git_pull(self, conn) -> None:
        pass

    def get_repository_root(self) -> str:
        """Return the absolute repository checkout root path when known."""

        target_path = str(getattr(self, "target_path", "") or "").rstrip("/")
        repo_name = str(getattr(self, "repo_name", "") or "").strip("/")
        if target_path and repo_name:
            return f"{target_path}/{repo_name}"
        return target_path or repo_name

    def repository_summary(self) -> dict[str, Any]:
        """Return non-IO metadata for repository overview screens."""

        deploy_keys = self.get_deploy_keys()
        return {
            "name": str(getattr(self, "repo_name", "") or getattr(self, "name", "-")),
            "url": self.get_url(),
            "root": self.get_repository_root(),
            "private": bool(getattr(self, "is_private", False)),
            "cloned": bool(getattr(self, "cloned", False)),
            "state": str(getattr(self, "state", "unknown")),
            "created": str(getattr(self, "created_timestamp", "") or ""),
            "modified": str(getattr(self, "modified_timestamp", "") or ""),
            "deploy_keys_available": bool(deploy_keys),
        }

    def get_deploy_keys(self) -> dict[str, str]:
        """Return deploy keys safe to show or copy in a UI."""

        return {}

    def list_repository_tree(self, conn) -> list[dict[str, Any]]:
        """List repository files for read-only browsing."""

        root = self.get_repository_root()
        if not root:
            return []
        return self.exec.fs_list_file_tree(conn, root)

    def read_repository_file(self, conn, path: str) -> str:
        """Read one repository file as text."""

        return str(self.exec.fs_read_file(conn, path, format="string"))


@dataclass
class AbstractModelRegistryService(ABC):
    """Service capability mixin for model registry services."""

    capabilities: ClassVar[set[ServiceCapability]] = {ServiceCapability.MODEL_REGISTRY}

    @abstractmethod
    def list_models(self, filter: str | None = None) -> List[Dict[str, Any]]:
        pass

    def load_artifact(
        self,
        model_name: str,
        model_version: str,
        artifact_path: str,
    ) -> Any | None:
        """Load a model artifact when supported by the registry implementation."""

        return None


@dataclass
class AbstractModelServerService(ABC):
    """Service capability mixin for model-serving services."""

    capabilities: ClassVar[set[ServiceCapability]] = {ServiceCapability.MODEL_SERVER}
    registry_uuid: str | None = field(default=None, kw_only=True)

    @abstractmethod
    def is_model(self, name: str) -> bool:
        pass

    @abstractmethod
    def get_registry(self) -> AbstractModelRegistryService | None:
        pass

    def list_supported_models(self) -> List[Dict[str, Any]]:
        """Return models this endpoint can serve or route to."""

        return []

    def get_example(
        self,
        model: Dict[str, Any] | None = None,
        input_example: Any | None = None,
    ) -> str:
        """Return a concrete invocation example for this model endpoint."""

        url = str(getattr(self, "service_url", "")).rstrip("/")
        if not url:
            return "No endpoint URL is available yet."
        body = input_example if input_example is not None else {}
        if isinstance(body, str):
            try:
                body = json.loads(body)
            except json.JSONDecodeError:
                pass
        return (
            "curl -k "
            f"{url} "
            "-H 'Content-Type: application/json' "
            f"-d '{json.dumps(body)}'"
        )


class AbstractMonitorService(ABC):
    """Service capability mixin for project-level monitoring providers."""

    capabilities: ClassVar[set[ServiceCapability]] = {ServiceCapability.MONITOR}

    @abstractmethod
    def get_monitor_snapshot(self, bundle: Any) -> Dict[str, Any]:
        """Return a compact host/resource monitoring snapshot for one bundle."""
        pass


@dataclass
class AbstractWorkflowOrchestratorService(ABC):
    """Service capability mixin for workflow orchestration providers."""

    capabilities: ClassVar[set[ServiceCapability]] = {
        ServiceCapability.WORKFLOW_ORCHESTRATOR
    }

    @abstractmethod
    def list_workflows(self) -> List[Dict[str, Any]]:
        """Return workflow/DAG metadata including recent run information."""
        pass


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

    state: Literal["un-initialized", "running", "stopped", "unknown"] = field(
        default="un-initialized", init=False
    )

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

    def render_template(
        self, template_name: str, variables: Mapping[str, Any]
    ) -> str:
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
            raise ValueError(f"Invalid template syntax in {template_path}: {exc}") from exc

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
        """Get a dependent service by UUID via the bound service lookup."""

        lookup = self._service_lookup
        if lookup is None:
            return None
        return lookup.get_service_by_uuid(service_uuid)

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
