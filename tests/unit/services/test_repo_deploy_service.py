from types import SimpleNamespace
import json
import shutil
import subprocess

import pytest
import yaml

from mlox.services.repo_deploy.service import RepoDeployDockerService
from mlox.service import ServiceCapability
from mlox.view.services.repo_deploy import _env_vars_to_text, _parse_env_text


BASE = {
    "name": "repo-deploy",
    "service_config_id": "cfg",
    "template": "/tmp/cfg.yaml",
    "target_path": "/tmp/stack",
}


class FakeExec:
    def __init__(self):
        self.calls = []
        self.files = {}
        self.appended = {}
        self.service_states = {}
        self.all_states = {}
        self.compose_status = ""

    def _record(self, name, *args, **kwargs):
        self.calls.append((name, args, kwargs))

    def fs_create_dir(self, conn, path):
        self._record("fs_create_dir", path)

    def fs_copy_remote_file(self, conn, src, dst):
        self._record("fs_copy_remote_file", src, dst)

    def fs_read_file(self, conn, path, format="yaml"):
        self._record("fs_read_file", path, format)
        value = self.files[path]
        return yaml.safe_load(value) if format == "yaml" and isinstance(value, str) else value

    def fs_create_empty_file(self, conn, path):
        self._record("fs_create_empty_file", path)
        self.appended[path] = []

    def fs_append_line(self, conn, path, line):
        self._record("fs_append_line", path, line)
        self.appended.setdefault(path, []).append(line)

    def fs_write_file(self, conn, path, content):
        self._record("fs_write_file", path, content)
        self.files[path] = content

    def docker_up(self, conn, compose_path, env_path):
        self._record("docker_up", compose_path, env_path)

    def docker_down(self, conn, compose_path, remove_volumes=False):
        self._record("docker_down", compose_path, remove_volumes)

    def docker_all_service_states(self, conn):
        self._record("docker_all_service_states")
        return self.all_states

    def docker_service_state(self, conn, service_name):
        self._record("docker_service_state", service_name)
        return self.service_states.get(service_name, "unknown")

    def fs_delete_dir(self, conn, path):
        self._record("fs_delete_dir", path)

    def execute(self, conn, command, **kwargs):
        self._record("execute", command, kwargs)
        if "ps --all --format json" in command:
            return self.compose_status

    def git_run(self, conn, git_args, *, working_dir, env=None, sudo=False, pty=False):
        self._record("git_run", git_args, working_dir, env, sudo, pty)


def _svc(compose_file="docker-compose.yaml"):
    service = RepoDeployDockerService(
        **BASE,
        repo_uuid="repo-uuid",
        compose_file=compose_file,
    )
    service.exec = FakeExec()
    service.get_dependent_service = lambda _uuid: SimpleNamespace(
        repo_name="my-repo",
        target_path="/repos",
    )
    return service


def test_env_text_helpers_parse_dotenv_style_content():
    text = "\n".join(
        [
            "# ignored",
            "A=1",
            "export B=two",
            "C=value=with=equals",
            "NO_EQUALS",
            "",
        ]
    )

    parsed = _parse_env_text(text)

    assert parsed == {"A": "1", "B": "two", "C": "value=with=equals"}
    assert _env_vars_to_text({"B": "2", "A": "1"}) == "A=1\nB=2"


def test_setup_discovers_services_ports_and_env_tokens():
    conn = SimpleNamespace(host="example.test")
    service = _svc("compose/app.yaml")
    service.exec.files["/repos/my-repo/compose/app.yaml"] = {
        "services": {
            "web": {
                "image": "nginx",
                "ports": ["${WEB_PORT:-8080}:80"],
                "environment": ["TZ=${TZ:-UTC}", "HELLO=world"],
            },
            "worker": {
                "image": "busybox",
                "ports": ["127.0.0.1:9090:9090", 9123],
            },
        }
    }

    service.setup(conn)

    assert service.compose_service_names == {"web": "web", "worker": "worker"}
    assert service.service_ports["web:1"] == 8080
    assert service.service_ports["worker:1"] == 9090
    assert service.service_ports["worker:2"] == 9123
    assert service.env_vars["WEB_PORT"] == "8080"
    assert service.env_vars["TZ"] == "UTC"
    assert service.target_path == "/repos/my-repo"
    assert service.target_docker_script == "compose/app.yaml"

    assert not any(c[0] == "fs_create_dir" for c in service.exec.calls)
    assert not any(c[0] == "fs_copy_remote_file" for c in service.exec.calls)

    env_lines = service.exec.appended["/repos/my-repo/.env"]
    assert "WEB_PORT=8080" in env_lines
    assert "TZ=UTC" in env_lines


def test_check_service_states_and_save_env_vars():
    conn = SimpleNamespace(host="example.test")
    service = _svc()
    service.compose_service_names = {"web": "web", "db": "db"}

    service.exec.compose_status = json.dumps([
        {"Service": "web", "State": "running"},
        {"Service": "db", "State": "running"},
    ])
    assert service.check(conn)["status"] == "running"

    service.exec.compose_status = "\n".join(json.dumps(item) for item in [
        {"Service": "web", "State": "created"},
        {"Service": "db", "State": "running"},
    ])
    assert service.check(conn)["status"] == "starting"

    service.save_env_vars(conn, {"A": "1", "B": "2"})
    assert service.env_vars == {"A": "1", "B": "2"}
    assert service.exec.appended["/repos/my-repo/.env"] == ["A=1", "B=2"]


def test_repo_deploy_advertises_runtime_capabilities():
    service = _svc()
    assert {ServiceCapability.APP, ServiceCapability.HEALTH,
            ServiceCapability.SECRET_MANAGER_BINDING,
            ServiceCapability.TELEMETRY_BINDING} <= service.capabilities


def test_setup_applies_providers_bound_before_initialization():
    service = _svc()
    service.secret_manager_uuid = "secrets"
    service.telemetry_uuid = "otel"
    service.get_bound_secret_manager_env_binding = lambda: {"TOKEN": "value"}
    service.get_bound_telemetry_env_binding = lambda: {"OTEL_EXPORTER_OTLP_ENDPOINT": "http://otel:4318"}
    service.exec.files["/repos/my-repo/docker-compose.yaml"] = {
        "services": {"app": {"image": "demo"}}
    }
    service.setup(object())
    for binding in ("secret-manager", "telemetry"):
        assert "app" in yaml.safe_load(service.exec.files[service._binding_path(binding)])["services"]
    service.spin_up(object())
    command = [call[1][0] for call in service.exec.calls if call[0] == "execute" and " up " in call[1][0]][-1]
    assert service._binding_path("secret-manager") in command
    assert service._binding_path("telemetry") in command


def test_health_reports_unhealthy_or_missing_compose_services():
    service = _svc()
    service.compose_service_names = {"web": "web", "worker": "worker"}
    service.exec.compose_status = json.dumps([
        {"Service": "web", "State": "running", "Health": "unhealthy"},
        {"Service": "worker", "State": "running"},
    ])
    health = service.get_health(object())
    assert health["status"] == "error"
    assert health["services"] == {"web": "unhealthy", "worker": "running"}
    assert health["healthy"] is False
    service.exec.compose_status = json.dumps([{"Service": "web", "State": "running"}])
    assert service.check(object())["status"] == "unknown"


def test_bindings_add_compose_overrides_and_unbind_independently():
    service = _svc()
    service.state = "running"
    service.compose_service_names = {"app": "app", "worker": "worker"}
    service.secret_manager_uuid = "secrets"
    service._apply_secret_manager_binding(
        object(), manager_uuid="secrets", environment={"TOKEN": "secret$value"}
    )
    secret_path = service._binding_path("secret-manager")
    secret_override = yaml.safe_load(service.exec.files[secret_path])
    assert secret_override["services"]["app"]["environment"]["TOKEN"] == "secret$$value"
    assert secret_override["services"]["worker"]["environment"]["TOKEN"] == "secret$$value"
    service.telemetry_uuid = "otel"
    service._apply_telemetry_binding(
        object(), telemetry_uuid="otel", environment={"OTEL_EXPORTER_OTLP_ENDPOINT": "http://otel:4318"}
    )
    telemetry_path = service._binding_path("telemetry")
    command = [call[1][0] for call in service.exec.calls if call[0] == "execute" and " up " in call[1][0]][-1]
    assert secret_path in command and telemetry_path in command
    service._remove_secret_manager_binding(object())
    command = [call[1][0] for call in service.exec.calls if call[0] == "execute" and " up " in call[1][0]][-1]
    assert secret_path not in command and telemetry_path in command
    assert any("chmod 600" in call[1][0] for call in service.exec.calls if call[0] == "execute")


def test_provider_binding_api_applies_and_removes_override():
    service = _svc()
    service.state = "running"
    service.compose_service_names = {"app": "app"}
    revoked = []
    provider = SimpleNamespace(
        get_secret_manager_env_binding=lambda uuid: {"TOKEN": f"token-{uuid}"},
        revoke_secret_manager_env_binding=revoked.append,
    )
    service._get_secret_manager_provider = lambda uuid: provider
    service.bind_secret_manager("manager", object())
    assert service.secret_manager_uuid == "manager"
    path = service._binding_path("secret-manager")
    assert yaml.safe_load(service.exec.files[path])["services"]["app"]["environment"]["TOKEN"] == f"token-{service.uuid}"
    service.unbind_secret_manager(object())
    assert service.secret_manager_uuid is None
    assert revoked == [service.uuid]


def test_binding_failure_restores_previous_override():
    service = _svc()
    service.state = "running"
    service.secret_manager_uuid = "new-manager"
    service.compose_service_names = {"app": "app"}
    service._use_repo_runtime_paths()
    path = service._binding_path("secret-manager")
    service.exec.files[path] = "previous override"

    def fail(*args, **kwargs):
        raise RuntimeError("compose failed")

    service._compose_up = fail
    with pytest.raises(RuntimeError, match="compose failed"):
        service._apply_secret_manager_binding(object(), manager_uuid="new-manager", environment={"TOKEN": "new"})
    assert service.exec.files[path] == "previous override"


@pytest.mark.skipif(shutil.which("docker") is None, reason="Docker CLI unavailable")
def test_binding_override_is_merged_into_compose_containers(tmp_path):
    service = _svc()
    service.compose_service_names = {"app": "app", "worker": "worker"}
    service._write_binding(object(), "secret-manager", {"TOKEN": "literal$value"})
    override = service.exec.files[service._binding_path("secret-manager")]
    (tmp_path / "compose.yaml").write_text(
        "services:\n  app:\n    image: example\n    environment:\n      EXISTING: kept\n"
        "  worker:\n    image: example\n"
    )
    (tmp_path / "binding.yaml").write_text(override)
    result = subprocess.run(
        ["docker", "compose", "-f", "compose.yaml", "-f", "binding.yaml", "config", "--format", "json"],
        cwd=tmp_path, capture_output=True, text=True, check=True,
    )
    config = json.loads(result.stdout)
    # Compose config preserves the escaped dollar in its reusable output.
    assert config["services"]["app"]["environment"] == {"EXISTING": "kept", "TOKEN": "literal$$value"}
    assert config["services"]["worker"]["environment"]["TOKEN"] == "literal$$value"


def test_redeploy_updates_binding_overrides_for_new_compose_services():
    service = _svc("compose/app.yaml")
    service._use_repo_runtime_paths()
    service.secret_manager_uuid = "secrets"
    service.compose_service_names = {"app": "app"}
    service._write_binding(object(), "secret-manager", {"TOKEN": "x$y"})
    service.exec.files["/repos/my-repo/compose/app.yaml"] = {
        "services": {"app": {"image": "demo"}, "worker": {"image": "demo"}}
    }
    service.update_and_redeploy(object())
    override = yaml.safe_load(service.exec.files[service._binding_path("secret-manager")])
    assert set(override["services"]) == {"app", "worker"}
    assert override["services"]["worker"]["environment"]["TOKEN"] == "x$$y"


def test_save_env_text_writes_raw_content_and_updates_env_vars():
    conn = SimpleNamespace(host="example.test")
    service = _svc()
    content = "# keep comment\nA=1\nexport B=two"

    service.save_env_text(conn, content, _parse_env_text(content))

    assert service.env_vars == {"A": "1", "B": "two"}
    assert service.exec.files["/repos/my-repo/.env"] == f"{content}\n"
    assert any(c[0] == "fs_write_file" for c in service.exec.calls)


def test_teardown_stops_compose_without_deleting_repo_dir():
    conn = SimpleNamespace(host="example.test")
    service = _svc("compose/app.yaml")

    service.teardown(conn)

    execute_calls = [c for c in service.exec.calls if c[0] == "execute"]
    expected = (
        "docker compose --project-directory /repos/my-repo "
        "--env-file /repos/my-repo/.env "
        "-f /repos/my-repo/compose/app.yaml down --volumes --remove-orphans"
    )
    assert any(expected in c[1][0] for c in execute_calls)
    assert not any(c[0] == "fs_delete_dir" for c in service.exec.calls)


def test_update_and_redeploy_pulls_repo_and_restarts_compose():
    conn = SimpleNamespace(host="example.test")
    pulled = {"called": False}

    class _RepoSvc:
        repo_name = "my-repo"
        target_path = "/repos"

        def git_pull(self, _conn):
            pulled["called"] = True

    service = RepoDeployDockerService(
        **BASE,
        repo_uuid="repo-uuid",
        compose_file="compose/app.yaml",
    )
    service.exec = FakeExec()
    service.env_vars = {"A": "1"}
    service.get_dependent_service = lambda _uuid: _RepoSvc()
    service.exec.files["/repos/my-repo/compose/app.yaml"] = {
        "services": {"app": {"image": "demo", "ports": ["8080:8080"]}}
    }

    service.update_and_redeploy(conn, compose_service="app")

    assert pulled["called"] is True
    execute_calls = [c for c in service.exec.calls if c[0] == "execute"]
    expected = (
        "docker compose --project-directory /repos/my-repo "
        "--env-file /repos/my-repo/.env "
        "-f /repos/my-repo/compose/app.yaml up --build -d app"
    )
    assert any(expected in c[1][0] for c in execute_calls)
    assert any(c[1][1]["sudo"] is True for c in execute_calls)
    assert service.exec.appended["/repos/my-repo/.env"] == ["A=1"]
    assert service.state == "running"


def test_setup_uses_container_port_when_host_port_token_is_empty():
    conn = SimpleNamespace(host="example.test")
    service = _svc("compose/redis.yaml")
    service.exec.files["/repos/my-repo/compose/redis.yaml"] = {
        "services": {
            "redis": {
                "image": "redis",
                "ports": ["${MY_REDIS_PORT:-}:6379"],
                "environment": ["REDIS_PASSWORD=${MY_REDIS_PW:-}"],
            }
        }
    }

    service.setup(conn)

    assert service.service_ports["redis:1"] == 6379
    assert service.env_vars["MY_REDIS_PORT"] == ""
    assert service.env_vars["MY_REDIS_PW"] == ""
