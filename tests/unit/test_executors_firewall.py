from mlox.executors import UbuntuTaskExecutor, TaskGroup


class DummyConn:
    pass


def test_firewall_up_uses_ufw_allow_and_enable(monkeypatch):
    executor = UbuntuTaskExecutor()
    calls = []

    def fake_run_task(connection, *, group, command, sudo=False, pty=False, description=None, extra_metadata=None):
        calls.append((group, command, sudo))
        return "ok"

    monkeypatch.setattr(executor, "_run_task", fake_run_task)

    result = executor.firewall_up(DummyConn(), [22, 8080, 8080])

    assert result == "ok"
    assert calls == [
        (TaskGroup.NETWORKING, "ufw allow 22/tcp", True),
        (TaskGroup.NETWORKING, "ufw allow 8080/tcp", True),
        (TaskGroup.NETWORKING, "ufw --force enable", True),
    ]


def test_firewall_down_uses_ufw_disable(monkeypatch):
    executor = UbuntuTaskExecutor()
    calls = []

    def fake_run_task(connection, *, group, command, sudo=False, pty=False, description=None, extra_metadata=None):
        calls.append((group, command, sudo))
        return "disabled"

    monkeypatch.setattr(executor, "_run_task", fake_run_task)

    result = executor.firewall_down(DummyConn())

    assert result == "disabled"
    assert calls == [(TaskGroup.NETWORKING, "ufw --force disable", True)]
