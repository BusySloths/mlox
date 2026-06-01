import re
import logging
import shlex
from dataclasses import dataclass, field
from typing import Any, Dict

from mlox.execution import TaskGroup
from mlox.service import AbstractService

logger = logging.getLogger(__name__)

_ENV_TOKEN_PATTERN = re.compile(
    r"\$\{([A-Za-z_][A-Za-z0-9_]*)(?:(?::-|-)([^}]*))?\}"
)


@dataclass
class RepoDeployDockerService(AbstractService):
    repo_uuid: str
    compose_file: str
    env_vars: Dict[str, str] = field(default_factory=dict)
    target_docker_env: str = field(default=".env", init=False)

    def _get_repo_service(self):
        repo_service = self.get_dependent_service(self.repo_uuid)
        if repo_service is None:
            raise ValueError(
                f"Dependent repository service could not be found for uuid '{self.repo_uuid}'"
            )
        return repo_service

    def _get_repo_root(self):
        repo_service = self._get_repo_service()
        repo_name = getattr(repo_service, "repo_name", "")
        repo_target_path = getattr(repo_service, "target_path", "")
        if not repo_name or not repo_target_path:
            raise ValueError(
                "Dependent repository service does not expose a usable repository path"
            )
        return f"{repo_target_path}/{repo_name}"

    def _use_repo_runtime_paths(self, repo_root: str | None = None) -> str:
        repo_root = repo_root or self._get_repo_root()
        compose_file = self.compose_file.lstrip("/")
        self.target_path = repo_root
        self.target_docker_script = compose_file
        return f"{repo_root}/{compose_file}"

    def _env_file_path(self) -> str:
        return f"{self.target_path}/{self.target_docker_env}"

    def _compose_up(self, conn, compose_service: str = "") -> bool:
        compose_path = self._use_repo_runtime_paths()
        compose_cmd = (
            f"docker compose --project-directory {shlex.quote(self.target_path)} "
            f"--env-file {shlex.quote(self._env_file_path())} "
            f"-f {shlex.quote(compose_path)} up --build -d"
        )
        if compose_service:
            compose_cmd = f"{compose_cmd} {shlex.quote(compose_service)}"
        self.exec.execute(
            conn,
            compose_cmd,
            group=TaskGroup.CONTAINER_RUNTIME,
            sudo=True,
        )
        self.state = "running"
        return True

    def _compose_down(self, conn, *, remove_volumes: bool = False) -> bool:
        compose_path = self._use_repo_runtime_paths()
        compose_cmd = (
            f"docker compose --project-directory {shlex.quote(self.target_path)} "
            f"--env-file {shlex.quote(self._env_file_path())} "
            f"-f {shlex.quote(compose_path)} down"
        )
        if remove_volumes:
            compose_cmd = f"{compose_cmd} --volumes"
        compose_cmd = f"{compose_cmd} --remove-orphans"
        self.exec.execute(
            conn,
            compose_cmd,
            group=TaskGroup.CONTAINER_RUNTIME,
            sudo=True,
        )
        self.state = "stopped"
        return True

    @staticmethod
    def _extract_tokens(value: Any) -> Dict[str, str]:
        found: Dict[str, str] = {}
        if isinstance(value, str):
            for key, default in _ENV_TOKEN_PATTERN.findall(value):
                found[key] = default or ""
        elif isinstance(value, dict):
            for nested in value.values():
                found.update(RepoDeployDockerService._extract_tokens(nested))
        elif isinstance(value, list):
            for nested in value:
                found.update(RepoDeployDockerService._extract_tokens(nested))
        return found

    def _discover_from_compose(self, conn, compose_path: str) -> None:
        compose_data = self.exec.fs_read_file(conn, compose_path, format="yaml")
        if not isinstance(compose_data, dict):
            raise ValueError(f"Compose file does not contain a YAML mapping: {compose_path}")

        services = compose_data.get("services", {})
        if not isinstance(services, dict) or not services:
            raise ValueError(
                f"Compose file does not contain a non-empty 'services' mapping: {compose_path}"
            )

        compose_labels: Dict[str, str] = {}
        discovered_ports: Dict[str, int] = {}
        discovered_env = dict(self.env_vars)

        for service_name, service_cfg in services.items():
            if not isinstance(service_cfg, dict):
                continue

            compose_labels[service_name] = service_name
            token_defaults = self._extract_tokens(service_cfg)
            for key, default in token_defaults.items():
                discovered_env.setdefault(key, default)

            for idx, entry in enumerate(service_cfg.get("ports", [])):
                host_port: int | None = None
                if isinstance(entry, int):
                    host_port = entry
                elif isinstance(entry, str):
                    normalized = entry.split("/", 1)[0]
                    token_match = _ENV_TOKEN_PATTERN.search(normalized)
                    if token_match:
                        token_name = token_match.group(1)
                        token_default = token_match.group(2) or ""
                        discovered_env.setdefault(token_name, token_default)
                        candidate = discovered_env.get(token_name, token_default)
                        if str(candidate).isdigit():
                            host_port = int(candidate)
                        else:
                            parts = normalized.split(":")
                            if len(parts) >= 2 and parts[-1].isdigit():
                                host_port = int(parts[-1])
                    else:
                        parts = normalized.split(":")
                        if len(parts) >= 2 and parts[-2].isdigit():
                            host_port = int(parts[-2])
                        elif len(parts) >= 1 and parts[0].isdigit():
                            host_port = int(parts[0])

                if host_port is not None:
                    key = f"{service_name}:{idx + 1}"
                    discovered_ports[key] = host_port

        self.compose_service_names = compose_labels
        self.service_ports = discovered_ports
        self.env_vars = discovered_env

    def setup(self, conn) -> None:
        compose_source = self._use_repo_runtime_paths()

        # Compose requires the env file to exist before `docker compose up`.
        env_file_path = self._env_file_path()
        self.exec.fs_create_empty_file(conn, env_file_path)

        self._discover_from_compose(conn, compose_source)

        for key, value in self.env_vars.items():
            self.exec.fs_append_line(conn, env_file_path, f"{key}={value}")

    def teardown(self, conn) -> None:
        self._compose_down(conn, remove_volumes=True)

    def spin_up(self, conn) -> bool:
        return self._compose_up(conn)

    def spin_down(self, conn) -> bool:
        return self._compose_down(conn, remove_volumes=True)

    def check(self, conn) -> Dict[str, str]:
        statuses = self.compose_service_status(conn)
        if not statuses:
            return {"status": "unknown", "services": {}}

        service_states = [str(v).lower() for v in statuses.values()]
        if all("running" in state for state in service_states):
            return {"status": "running", "services": statuses}
        if any(state in {"created", "restarting", "starting"} for state in service_states):
            return {"status": "starting", "services": statuses}
        if all(state in {"exited", "dead", "stopped"} for state in service_states):
            return {"status": "stopped", "services": statuses}
        return {"status": "unknown", "services": statuses}

    def get_secrets(self) -> Dict[str, Dict]:
        return {}

    def save_env_vars(self, conn, env_vars: Dict[str, str]) -> None:
        self.env_vars = dict(env_vars)
        self._use_repo_runtime_paths()
        env_file_path = self._env_file_path()
        self.exec.fs_create_empty_file(conn, env_file_path)
        for key, value in self.env_vars.items():
            self.exec.fs_append_line(conn, env_file_path, f"{key}={value}")

    def save_env_text(self, conn, env_text: str, env_vars: Dict[str, str]) -> None:
        self.env_vars = dict(env_vars)
        self._use_repo_runtime_paths()
        content = env_text
        if content and not content.endswith("\n"):
            content += "\n"
        self.exec.fs_write_file(conn, self._env_file_path(), content)

    def update_and_redeploy(self, conn, compose_service: str = "app") -> None:
        repo_service = self._get_repo_service()
        repo_root = self._get_repo_root()
        compose_source = self._use_repo_runtime_paths(repo_root)

        if hasattr(repo_service, "git_pull"):
            repo_service.git_pull(conn)
        elif hasattr(self.exec, "git_run"):
            self.exec.git_run(conn, ["pull"], working_dir=repo_root)
        else:
            self.exec.execute(
                conn,
                f"cd {shlex.quote(repo_root)} && git pull",
                group=TaskGroup.VERSION_CONTROL,
            )

        self._discover_from_compose(conn, compose_source)
        self.save_env_vars(conn, self.env_vars)
        self._compose_up(conn, compose_service=compose_service)
