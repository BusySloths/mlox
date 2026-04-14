from mlox.executors import UbuntuTaskExecutor, TaskGroup


class DummyConn:
    pass


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
        command
        for group, command, sudo in calls
        if group == TaskGroup.NETWORKING and sudo
    ]


def test_firewall_up_creates_native_and_docker_rules(monkeypatch):
    executor = UbuntuTaskExecutor()
    calls = _capture_run_task(executor, monkeypatch, ["Status: active"])

    result = executor.firewall_up(DummyConn(), [22, 8080, 8080])

    assert result == "Status: active"
    assert _network_commands(calls) == [
        *UbuntuTaskExecutor._iptables_setup_commands(),
        "iptables -F MLOX-FIREWALL",
        "iptables -F MLOX-DOCKER-FIREWALL",
        "iptables -A MLOX-FIREWALL -i lo -j ACCEPT",
        (
            "iptables -A MLOX-FIREWALL -m conntrack "
            "--ctstate ESTABLISHED,RELATED -j ACCEPT"
        ),
        (
            "iptables -A MLOX-DOCKER-FIREWALL -m conntrack "
            "--ctstate ESTABLISHED,RELATED -j ACCEPT"
        ),
        "iptables -A MLOX-DOCKER-FIREWALL -i docker0 -j RETURN",
        "iptables -A MLOX-DOCKER-FIREWALL -i br+ -j RETURN",
        "iptables -A MLOX-FIREWALL -p tcp --dport 22 -j ACCEPT",
        (
            "iptables -A MLOX-DOCKER-FIREWALL -p tcp "
            "-m conntrack --ctorigdstport 22 -j ACCEPT"
        ),
        "iptables -A MLOX-FIREWALL -p tcp --dport 8080 -j ACCEPT",
        (
            "iptables -A MLOX-DOCKER-FIREWALL -p tcp "
            "-m conntrack --ctorigdstport 8080 -j ACCEPT"
        ),
        "iptables -A MLOX-FIREWALL -j DROP",
        (
            "iptables -A MLOX-DOCKER-FIREWALL -o docker0 "
            "-m conntrack --ctstate NEW -j DROP"
        ),
        (
            "iptables -A MLOX-DOCKER-FIREWALL -o br+ "
            "-m conntrack --ctstate NEW -j DROP"
        ),
        UbuntuTaskExecutor._iptables_status_command(),
    ]


def test_firewall_up_supports_per_port_source_whitelists(monkeypatch):
    executor = UbuntuTaskExecutor()
    calls = _capture_run_task(executor, monkeypatch, ["Status: active"])

    result = executor.firewall_up(
        DummyConn(),
        [22, 8080, 9090],
        source_ips_by_port={
            8080: ["203.0.113.10", "203.0.113.0/24"],
            9090: [],
        },
    )

    assert result == "Status: active"
    commands = _network_commands(calls)
    assert commands[:5] == UbuntuTaskExecutor._iptables_setup_commands()
    assert commands[5:] == [
        "iptables -F MLOX-FIREWALL",
        "iptables -F MLOX-DOCKER-FIREWALL",
        "iptables -A MLOX-FIREWALL -i lo -j ACCEPT",
        (
            "iptables -A MLOX-FIREWALL -m conntrack "
            "--ctstate ESTABLISHED,RELATED -j ACCEPT"
        ),
        (
            "iptables -A MLOX-DOCKER-FIREWALL -m conntrack "
            "--ctstate ESTABLISHED,RELATED -j ACCEPT"
        ),
        "iptables -A MLOX-DOCKER-FIREWALL -i docker0 -j RETURN",
        "iptables -A MLOX-DOCKER-FIREWALL -i br+ -j RETURN",
        "iptables -A MLOX-FIREWALL -p tcp --dport 22 -j ACCEPT",
        (
            "iptables -A MLOX-DOCKER-FIREWALL -p tcp "
            "-m conntrack --ctorigdstport 22 -j ACCEPT"
        ),
        (
            "iptables -A MLOX-FIREWALL -p tcp -s 203.0.113.0/24 "
            "--dport 8080 -j ACCEPT"
        ),
        (
            "iptables -A MLOX-DOCKER-FIREWALL -p tcp -s 203.0.113.0/24 "
            "-m conntrack --ctorigdstport 8080 -j ACCEPT"
        ),
        ("iptables -A MLOX-FIREWALL -p tcp -s 203.0.113.10 " "--dport 8080 -j ACCEPT"),
        (
            "iptables -A MLOX-DOCKER-FIREWALL -p tcp -s 203.0.113.10 "
            "-m conntrack --ctorigdstport 8080 -j ACCEPT"
        ),
        "iptables -A MLOX-FIREWALL -p tcp --dport 9090 -j ACCEPT",
        (
            "iptables -A MLOX-DOCKER-FIREWALL -p tcp "
            "-m conntrack --ctorigdstport 9090 -j ACCEPT"
        ),
        "iptables -A MLOX-FIREWALL -j DROP",
        (
            "iptables -A MLOX-DOCKER-FIREWALL -o docker0 "
            "-m conntrack --ctstate NEW -j DROP"
        ),
        (
            "iptables -A MLOX-DOCKER-FIREWALL -o br+ "
            "-m conntrack --ctstate NEW -j DROP"
        ),
        UbuntuTaskExecutor._iptables_status_command(),
    ]


def test_firewall_up_accepts_port_source_mapping(monkeypatch):
    executor = UbuntuTaskExecutor()
    calls = _capture_run_task(executor, monkeypatch, ["Status: active"])

    result = executor.firewall_up(
        DummyConn(),
        {
            22: None,
            8080: ["203.0.113.10"],
        },
    )

    assert result == "Status: active"
    commands = _network_commands(calls)
    assert "iptables -A MLOX-FIREWALL -p tcp --dport 22 -j ACCEPT" in commands
    assert (
        "iptables -A MLOX-FIREWALL -p tcp -s 203.0.113.10 " "--dport 8080 -j ACCEPT"
    ) in commands
    assert "iptables -A MLOX-FIREWALL -j DROP" in commands


def test_firewall_down_removes_managed_chains(monkeypatch):
    executor = UbuntuTaskExecutor()
    calls = _capture_run_task(executor, monkeypatch)

    result = executor.firewall_down(DummyConn())

    assert result == "ok"
    assert _network_commands(calls) == UbuntuTaskExecutor._iptables_teardown_commands()


def test_firewall_status_uses_iptables_status_script(monkeypatch):
    executor = UbuntuTaskExecutor()
    calls = _capture_run_task(executor, monkeypatch, ["Status: active"])

    result = executor.firewall_status(DummyConn())

    assert result == "Status: active"
    assert _network_commands(calls) == [UbuntuTaskExecutor._iptables_status_command()]


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


def test_firewall_update_noops_when_inactive(monkeypatch):
    executor = UbuntuTaskExecutor()
    calls = _capture_run_task(executor, monkeypatch, ["Status: inactive"])

    result = executor.firewall_update(DummyConn(), [22, 8080])

    assert result == "Status: inactive"
    assert _network_commands(calls) == [UbuntuTaskExecutor._iptables_status_command()]


def test_firewall_update_rebuilds_rules_when_active(monkeypatch):
    executor = UbuntuTaskExecutor()
    calls = _capture_run_task(
        executor,
        monkeypatch,
        [
            "Status: active\n-A MLOX-FIREWALL -p tcp -m tcp --dport 9090 -j ACCEPT",
            "Status: active",
        ],
    )

    result = executor.firewall_update(DummyConn(), [22, 8080, 8080])

    assert result == "Status: active"
    commands = _network_commands(calls)
    assert commands[0] == UbuntuTaskExecutor._iptables_status_command()
    assert commands[1:6] == UbuntuTaskExecutor._iptables_setup_commands()
    assert "iptables -A MLOX-FIREWALL -p tcp --dport 22 -j ACCEPT" in commands
    assert "iptables -A MLOX-FIREWALL -p tcp --dport 8080 -j ACCEPT" in commands
    assert commands[-1] == UbuntuTaskExecutor._iptables_status_command()


def test_firewall_update_rebuilds_source_specific_rules(monkeypatch):
    executor = UbuntuTaskExecutor()
    calls = _capture_run_task(
        executor,
        monkeypatch,
        [
            "Status: active\n-A MLOX-FIREWALL -p tcp -m tcp --dport 8080 -j ACCEPT",
            "Status: active",
        ],
    )

    result = executor.firewall_update(
        DummyConn(),
        [22, 8080, 9090],
        source_ips_by_port={
            8080: ["203.0.113.10", "203.0.113.0/24"],
            9090: [],
        },
    )

    assert result == "Status: active"
    commands = _network_commands(calls)
    assert (
        "iptables -A MLOX-FIREWALL -p tcp -s 203.0.113.10 " "--dport 8080 -j ACCEPT"
    ) in commands
    assert "iptables -A MLOX-FIREWALL -j DROP" in commands
    assert "iptables -A MLOX-FIREWALL -p tcp --dport 9090 -j ACCEPT" in commands
