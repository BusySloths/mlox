import shlex

from mlox.executors import UbuntuTaskExecutor, TaskGroup
from mlox.firewall import FirewallPolicy
import pytest


class DummyConn:
    pass


def test_apply_policy_reports_failed_sudo_command(monkeypatch):
    executor = UbuntuTaskExecutor()
    monkeypatch.setattr(executor, "_run_task", lambda *a, **k: None)
    with pytest.raises(RuntimeError, match="partially changed"):
        executor.firewall_apply_policy(DummyConn(), FirewallPolicy((22, 80, 443)), 22, docker=True)


def test_persist_policy_reports_sudo_failure(monkeypatch):
    executor = UbuntuTaskExecutor()
    monkeypatch.setattr(executor, "_run_task", lambda *a, **k: None)
    with pytest.raises(RuntimeError, match="match the draft"):
        executor.firewall_persist_policy(DummyConn(), FirewallPolicy((22, 80, 443)), 22, docker=True)


def test_apply_policy_rejects_changed_ssh_port_before_running_command(monkeypatch):
    executor = UbuntuTaskExecutor()
    calls = _capture_run_task(executor, monkeypatch)
    with pytest.raises(ValueError, match="SSH port"):
        executor.firewall_apply_policy(DummyConn(), FirewallPolicy((22, 80, 443)), 2222, docker=True)
    assert calls == []


def _capture_run_task(executor, monkeypatch, status_responses=None):
    calls = []
    responses = list(status_responses or [])

    def fake_run_task(
        connection,
        *,
        group,
        command,
        sudo=False,
        pty=False,
        description=None,
        extra_metadata=None,
    ):
        calls.append((group, command, sudo))
        if command == UbuntuTaskExecutor._iptables_status_command() and responses:
            return responses.pop(0)
        return "ok"

    monkeypatch.setattr(executor, "_run_task", fake_run_task)
    return calls


def _network_commands(calls):
    return [
        _unwrap_root_shell_command(command)
        for group, command, sudo in calls
        if group == TaskGroup.NETWORKING and sudo
    ]


def _unwrap_root_shell_command(command):
    parts = shlex.split(command)
    if parts[:2] == ["sh", "-c"] and len(parts) == 3:
        return parts[2]
    return command


def _iptables_teardown_scripts():
    return [
        _unwrap_root_shell_command(command)
        for command in UbuntuTaskExecutor._iptables_teardown_commands()
    ]


def _iptables_status_script():
    return _unwrap_root_shell_command(UbuntuTaskExecutor._iptables_status_command())


def test_firewall_commands_run_through_root_shell():
    commands = [
        *UbuntuTaskExecutor._iptables_teardown_commands(),
        UbuntuTaskExecutor._iptables_status_command(),
    ]

    for command in commands:
        parts = shlex.split(command)
        assert parts[:2] == ["sh", "-c"]
        assert len(parts) == 3

    assert _iptables_status_script().startswith("if iptables -C")


def test_firewall_down_removes_managed_chains(monkeypatch):
    executor = UbuntuTaskExecutor()
    calls = _capture_run_task(executor, monkeypatch)

    result = executor.firewall_down(DummyConn())

    assert result == "ok"
    commands = _network_commands(calls)
    assert "MLOX-POLICY-IN" in commands[0]
    assert commands[1:] == _iptables_teardown_scripts()


def test_firewall_status_uses_iptables_status_script(monkeypatch):
    executor = UbuntuTaskExecutor()
    calls = _capture_run_task(executor, monkeypatch, ["Status: active"])

    result = executor.firewall_status(DummyConn())

    assert result == "Status: active"
    assert _network_commands(calls) == [_iptables_status_script()]


def test_parse_iptables_allowed_ports_and_rules():
    status = """Status: active
-N MLOX-FIREWALL
-A MLOX-FIREWALL -p tcp -m tcp --dport 22 -j ACCEPT
-A MLOX-FIREWALL -p tcp -m tcp --dport 8080 -j ACCEPT
-A MLOX-FIREWALL -p tcp -m tcp --dport 9090 -j DROP
-A MLOX-FIREWALL -s 203.0.113.10/32 -p tcp -m tcp --dport 6000 -j ACCEPT
-A MLOX-DOCKER-FIREWALL -p tcp -m conntrack --ctorigdstport 50051 -j ACCEPT
-A MLOX-DOCKER-FIREWALL -s 203.0.113.0/24 -p tcp -m conntrack --ctorigdstport 7000 -j ACCEPT
"""

    assert UbuntuTaskExecutor._parse_iptables_allowed_ports(status) == {
        22,
        8080,
        50051,
        6000,
        7000,
    }
    assert UbuntuTaskExecutor._parse_iptables_allowed_rules(status) == {
        (22, None),
        (8080, None),
        (50051, None),
        (6000, "203.0.113.10"),
        (7000, "203.0.113.0/24"),
    }
    assert UbuntuTaskExecutor._parse_iptables_allowed_ports("Status: inactive") == set()
    assert UbuntuTaskExecutor._parse_iptables_allowed_ports(None) is None
