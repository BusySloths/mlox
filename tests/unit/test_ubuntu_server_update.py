from __future__ import annotations

from contextlib import contextmanager
from types import SimpleNamespace

from mlox.servers.ubuntu.native import UbuntuNativeServer


class FakeExec:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def sys_update_system_packages(self, conn) -> None:
        self.calls.append("sys_update_system_packages")


def test_ubuntu_native_update_delegates_to_system_executor():
    server = UbuntuNativeServer(
        ip="10.0.0.10",
        root="root",
        root_pw="pw",
        service_config_id="ubuntu-native",
    )
    fake_exec = FakeExec()
    server.exec = fake_exec

    @contextmanager
    def _cm():
        yield SimpleNamespace(host=server.ip)

    server.get_server_connection = lambda force_root=False: _cm()

    server.update()

    assert fake_exec.calls == ["sys_update_system_packages"]
