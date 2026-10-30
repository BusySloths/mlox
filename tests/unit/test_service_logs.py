from unittest.mock import MagicMock, patch
import pytest

from mlox.service import AbstractService
from mlox.executors import UbuntuTaskExecutor


class DummyService(AbstractService):
    def setup(self, conn):
        pass

    def teardown(self, conn):
        pass

    def check(self, conn):
        return {}

    def get_secrets(self) -> dict:
        return {}


def test_docker_log_tail_returns_stderr_stream_and_hides_sudo_prompt():
    conn = MagicMock()
    conn.sudo.return_value.exited = 0
    conn.sudo.return_value.stdout = "[sudo] password: log line\n"
    assert UbuntuTaskExecutor().docker_service_log_tails(conn, "otel-collector", 5) == "log line"


def test_docker_log_tail_reports_command_failure():
    conn = MagicMock()
    conn.sudo.return_value.exited = 1
    conn.sudo.return_value.stdout = "[sudo] password: container missing"
    with pytest.raises(RuntimeError, match="container missing"):
        UbuntuTaskExecutor().docker_service_log_tails(conn, "otel-collector", 5)


def test_compose_service_log_tail_direct_match():
    svc = DummyService(
        name="s", service_config_id="c", template="t", target_path="/tmp"
    )
    svc.compose_service_names = {"web": "web_service"}

    conn = MagicMock()
    conn.sudo.return_value.exited = 0
    conn.sudo.return_value.stdout = "web_service\n"

    svc.exec = MagicMock()
    svc.exec.docker_all_service_states.return_value = {
        "web_service": {"Status": "running"}
    }
    svc.exec.docker_service_log_tails.return_value = "line1\nline2"

    out = AbstractService.compose_service_log_tail(svc, conn, "web", tail=2)
    assert "line1" in out


def test_compose_service_log_tail_heuristic_match():
    svc = DummyService(
        name="s", service_config_id="c", template="t", target_path="/tmp"
    )
    svc.compose_service_names = {"db": "postgres"}

    conn = MagicMock()
    conn.sudo.return_value.exited = 0
    conn.sudo.return_value.stdout = "proj_postgres_1\n"

    svc.exec = MagicMock()
    svc.exec.docker_all_service_states.return_value = {
        "proj_postgres_1": {"Status": "running"}
    }
    svc.exec.docker_service_log_tails.return_value = "ok"

    out = AbstractService.compose_service_log_tail(svc, conn, "db", tail=10)
    assert out == "ok"


def test_compose_service_log_tail_no_match():
    svc = DummyService(
        name="s", service_config_id="c", template="t", target_path="/tmp"
    )
    svc.compose_service_names = {"x": "nope"}

    conn = MagicMock()
    conn.sudo.return_value.exited = 0
    conn.sudo.return_value.stdout = ""

    svc.exec = MagicMock()
    svc.exec.docker_all_service_states.return_value = {}
    svc.exec.docker_service_state.return_value = ""

    with pytest.raises(LookupError, match="not found"):
        AbstractService.compose_service_log_tail(svc, conn, "x", tail=5)
