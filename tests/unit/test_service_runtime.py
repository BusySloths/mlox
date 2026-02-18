from __future__ import annotations

from dataclasses import dataclass

from mlox.service import AbstractService


class _Exec:
    def __init__(self):
        self.history = [{"action": "one", "status": "ok"}]
        self.calls = []

    def docker_up(self, conn, compose, env):
        self.calls.append(("up", compose, env))

    def docker_down(self, conn, compose, remove_volumes=False):
        self.calls.append(("down", compose, remove_volumes))

    def docker_all_service_states(self, conn):
        return {
            "proj_api_1": {"Status": "running"},
            "db": {"State": "exited"},
        }

    def docker_service_state(self, conn, service):
        return "fallback"

    def docker_service_log_tails(self, conn, service, tail=200):
        return f"logs:{service}:{tail}"

    def fs_create_dir(self, conn, path):
        self.calls.append(("mkdir", path))

    def fs_touch(self, conn, path):
        self.calls.append(("touch", path))

    def fs_write_file(self, conn, path, content):
        self.calls.append(("write", path, str(content)[:30]))

    def fs_set_permissions(self, conn, path, mode):
        self.calls.append(("chmod", path, mode))


@dataclass
class _Service(AbstractService):
    def setup(self, conn):
        return None

    def teardown(self, conn):
        return None

    def check(self, conn):
        return {}

    def get_secrets(self):
        return {}


def _svc():
    svc = _Service(name="svc", service_config_id="cfg", template="t", target_path="/tmp/svc")
    svc.exec = _Exec()
    svc.compose_service_names = {"api": "api", "db": "db"}
    return svc


def test_compose_up_and_down_update_state():
    svc = _svc()

    assert svc.compose_up(conn=object()) is True
    assert svc.state == "running"

    assert svc.compose_down(conn=object(), remove_volumes=True) is True
    assert svc.state == "stopped"


def test_compose_service_status_and_logs_paths():
    svc = _svc()

    statuses = svc.compose_service_status(conn=object())
    assert statuses["db"] == "exited"

    assert svc.compose_service_log_tail(conn=object(), label="api", tail=10).startswith("logs:")
    assert svc.compose_service_log_tail(conn=object(), label="missing") == "Not found"


def test_dump_state_writes_debug_files():
    svc = _svc()

    svc.dump_state(conn=object())

    write_calls = [c for c in svc.exec.calls if c[0] == "write"]
    assert any("start.sh" in c[1] for c in write_calls)
    assert any("service-state.json" in c[1] for c in write_calls)
