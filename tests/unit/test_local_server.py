from types import SimpleNamespace
from unittest.mock import patch

from mlox.servers.local import LocalhostServer, LocalConnection


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


def test_localhost_server_customizes_service(monkeypatch):
    server = LocalhostServer(
        ip="127.0.0.1",
        root="tester",
        root_pw="",
        service_config_id="svc",
    )

    fake_service = SimpleNamespace(target_path="/tmp/example", name="svc")
    server.customize_service(fake_service)
    assert fake_service.target_path == str(server.base_path / "example")


def test_localhost_server_reports_docker_status(monkeypatch):
    server = LocalhostServer(
        ip="127.0.0.1",
        root="tester",
        root_pw="",
        service_config_id="svc",
    )

    with patch("mlox.servers.local.shutil.which", return_value="/usr/bin/docker"):
        with patch("mlox.servers.local.subprocess.run", return_value=SimpleNamespace(returncode=0)):
            server.setup_backend()

    status = server.get_backend_status()
    assert status["backend.is_running"] is True
    assert status["backend.docker.available"] is True
