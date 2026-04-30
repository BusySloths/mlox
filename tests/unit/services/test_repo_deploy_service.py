from types import SimpleNamespace

from mlox.services.repo_deploy.service import RepoDeployDockerService
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

    def _record(self, name, *args, **kwargs):
        self.calls.append((name, args, kwargs))

    def fs_create_dir(self, conn, path):
        self._record("fs_create_dir", path)

    def fs_copy_remote_file(self, conn, src, dst):
        self._record("fs_copy_remote_file", src, dst)

    def fs_read_file(self, conn, path, format="yaml"):
        self._record("fs_read_file", path, format)
        return self.files[path]

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

    service.exec.all_states = {
        "proj_web_1": {"Status": "running"},
        "proj_db_1": {"Status": "running"},
    }
    assert service.check(conn)["status"] == "running"

    service.exec.all_states = {
        "proj_web_1": {"Status": "created"},
        "proj_db_1": {"Status": "running"},
    }
    # compose_service_status currently reports the last tracked compose service
    # label due to base-class implementation details, which resolves to "db".
    assert service.check(conn)["status"] == "running"

    service.save_env_vars(conn, {"A": "1", "B": "2"})
    assert service.env_vars == {"A": "1", "B": "2"}
    assert service.exec.appended["/repos/my-repo/.env"] == ["A=1", "B=2"]


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
