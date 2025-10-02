from unittest.mock import MagicMock, patch

from mlox.service import AbstractService


class DummyService(AbstractService):
    def setup(self, conn):
        pass

    def teardown(self, conn):
        pass

    def check(self, conn):
        return {}

    def get_secrets(self) -> dict:
        return {}


def test_compose_service_log_tail_direct_match():
    svc = DummyService(
        name="s", service_config_id="c", template="t", target_path="/tmp"
    )
    svc.compose_service_names = {"web": "web_service"}

    conn = MagicMock()

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

    svc.exec = MagicMock()
    svc.exec.docker_all_service_states.return_value = {}
    svc.exec.docker_service_state.return_value = ""

    out = AbstractService.compose_service_log_tail(svc, conn, "x", tail=5)
    assert out == "Service with label x (nope) not found"
