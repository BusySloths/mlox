from dataclasses import dataclass
from types import SimpleNamespace
from unittest.mock import patch

from fabric import Connection  # type: ignore
from mlox.service import AbstractService
from mlox.infra import Infrastructure
from mlox.config import ServiceConfig, BuildConfig, get_stacks_path, load_config
from mlox.servers.local.local import LocalhostServer, LocalConnection


@dataclass
class ExampleService(AbstractService):
    def setup(self, conn: Connection) -> None:
        pass

    def teardown(self, conn: Connection) -> None:
        pass

    def check(self, conn: Connection) -> dict:
        return {"status": "running"}

    def get_secrets(self) -> dict:
        return {"example_service": {"secret_key": "secret_value"}}


def test_local_connection_executes_commands(tmp_path):
    conn = LocalConnection(base_path=tmp_path, host="127.0.0.1", user="tester")
    with conn as c:
        result = c.run("echo hello")
    assert result.return_code == 0
    assert "hello" in result.stdout


def test_local_connection_sudo_falls_back(tmp_path):
    conn = LocalConnection(base_path=tmp_path, host="127.0.0.1", user="tester")
    with patch("shutil.which", return_value=None):
        with conn as c:
            result = c.sudo("echo hi")
    assert result.return_code == 0
    assert "hi" in result.stdout


def test_localhost_server_adds_custom_service():
    server = LocalhostServer(
        ip="127.0.0.1",
        root="tester",
        root_pw="",
        service_config_id="svc",
    )

    infra = Infrastructure()

    server_config = load_config(
        get_stacks_path(prefix="mlox-server"), "/local", "mlox-server.local.yaml"
    )
    bundle = infra.add_server(server_config, {})

    build_config = BuildConfig(
        class_name="tests.unit.test_local_server.ExampleService",
        params={
            "target_path": "${MLOX_USER_HOME}/tmp/example",
            "service_config_id": "example",
            "template": "example_template",
            "name": "example_service",
        },
    )
    service_config = ServiceConfig(
        id="example",
        name="Example Service",
        maintainer="tester",
        description_short="An example",
        description="An example service",
        links={},
        version="0.1.0",
        build=build_config,
    )
    bundle = infra.add_service(server.ip, service_config, params={})
    assert bundle is not None
    assert len(bundle.services) == 1
    assert bundle.services[0].target_path == f"{server.mlox_user.home}/tmp/example"


def test_localhost_server_reports_docker_status(monkeypatch):
    server = LocalhostServer(
        ip="127.0.0.1",
        root="tester",
        root_pw="",
        service_config_id="svc",
    )

    with patch("mlox.servers.local.local.shutil.which", return_value="/usr/bin/docker"):
        with patch(
            "mlox.servers.local.local.subprocess.run",
            return_value=SimpleNamespace(returncode=0),
        ):
            server.setup_backend()

    status = server.get_backend_status()
    assert status["backend.is_running"] is True
    assert status["backend.docker.available"] is True
