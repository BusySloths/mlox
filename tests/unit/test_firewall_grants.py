from datetime import datetime, timedelta, timezone

import pytest

from mlox.firewall_grants import FirewallAccessGrant, active_source_expirations, ssh_client_address


def test_shared_address_keeps_latest_unexpired_grant():
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    first = FirewallAccessGrant("one", "192.0.2.10", now + timedelta(minutes=15))
    second = FirewallAccessGrant("two", "192.0.2.10", now + timedelta(hours=1))
    expired = FirewallAccessGrant("old", "192.0.2.20", now)
    assert active_source_expirations([first, second, expired], now=now) == {"192.0.2.10": second.expires_at}
    assert active_source_expirations([first, expired], now=now) == {"192.0.2.10": first.expires_at}
    assert active_source_expirations([expired], now=now) == {}


@pytest.mark.parametrize("value,expected", [("192.0.2.1 3456 198.51.100.1 22", "192.0.2.1"),
                                         ("2001:db8::1 44321 2001:db8::2 22", "2001:db8::1")])
def test_ssh_source_is_observed_per_connection(value, expected):
    assert ssh_client_address(value) == expected


@pytest.mark.parametrize("value", ["", "127.0.0.1 100 192.0.2.1 22", "192.0.2.1 nope 192.0.2.2 22", "192.0.2.1 42 invalid 22"])
def test_invalid_ssh_source_is_rejected(value):
    with pytest.raises(ValueError):
        ssh_client_address(value)


def test_tui_distinguishes_unavailable_empty_and_active_grants():
    from mlox.tui.screens.dashboard.firewall_panel import FirewallPanel

    assert FirewallPanel._temporary_access_summary({}) == "Unavailable"
    assert FirewallPanel._temporary_access_summary({"temporary_grants": []}) == "None"
    value = FirewallPanel._temporary_access_summary({"temporary_grants": [{"expires_at": "2099-01-01T12:00:00+00:00"}]})
    assert value.startswith("1 · ") and "unknown" not in value
    assert FirewallPanel._temporary_access_summary({"temporary_grants": [{"expires_at": "2000-01-01T12:00:00+00:00"}]}) == "None"


def test_tui_updates_only_reported_servers_after_access_changes():
    from types import SimpleNamespace
    from unittest.mock import Mock
    from mlox.application.result import OperationResult
    from mlox.tui.screens.dashboard.firewall_panel import FirewallPanel

    first = {"bundle": "one", "temporary_grants": []}
    second = {"bundle": "two", "temporary_grants": []}
    panel = SimpleNamespace(_rows=[first, second], _selected_id="", _set_loading=Mock(),
                            _populate_table=Mock(), notify=Mock())
    result = OperationResult(False, 4, "partial", {"grant_id": "abc", "servers": [
        {"server": "one", "status": "added", "address": "192.0.2.1", "expires_at": "2027-01-01T00:00:00+00:00"},
        {"server": "two", "status": "failed", "message": "offline"},
    ]})
    FirewallPanel._finish_access_action(panel, result, "15m", False)
    assert first["temporary_grants"][0]["address"] == "192.0.2.1"
    assert second["temporary_grants"] == []
    assert "two: offline" in panel.notify.call_args.args[0]


def test_observed_address_comes_from_the_same_ssh_connection():
    from types import SimpleNamespace
    from mlox.servers.ubuntu.firewall_grants import observed_ssh_client

    calls = []
    class Connection:
        def run(self, command, **kwargs):
            calls.append((command, kwargs))
            return SimpleNamespace(stdout="192.0.2.42 41573 198.51.100.3 22")
    assert observed_ssh_client(Connection()) == "192.0.2.42"
    assert "SSH_CONNECTION" in calls[0][0]
    assert calls[0][1]["pty"] is False


@pytest.mark.parametrize("address,tool,family", [("192.0.2.1", "iptables", 4), ("2001:db8::1", "ip6tables", 6)])
def test_runtime_grants_target_the_correct_server_paths(address, tool, family):
    from mlox.servers.ubuntu.firewall_grants import compile_grant_rules, grant_set_name

    grant_id = "12a6eb4e0e8d4b878adc59c09d343749"
    set_name = grant_set_name(grant_id, family)
    assert len(set_name) <= 31
    native = compile_grant_rules(grant_id, address, docker=False, k3s=False)
    docker = compile_grant_rules(grant_id, address, docker=True, k3s=False)
    k3s = compile_grant_rules(grant_id, address, docker=False, k3s=True)
    assert len(native) == 1 and native[0][0] == tool and native[0][-1] == "ACCEPT"
    assert len(docker) == 2 and docker[1][2] == "MLOX-POLICY-DOCKER" and docker[1][-1] == "RETURN"
    assert len(k3s) == 2 and k3s[1][1:3] == ("-t", "mangle") and k3s[1][-1] == "RETURN"
    assert all(set_name in rule and f"mlox-temp-{grant_id}" in rule for rule in (*docker, *k3s))


def test_runtime_grant_names_reject_invalid_ids_and_families():
    from mlox.servers.ubuntu.firewall_grants import grant_set_name

    with pytest.raises(ValueError):
        grant_set_name("not-a-uuid", 4)
    with pytest.raises(ValueError):
        grant_set_name("12a6eb4e0e8d4b878adc59c09d343749", 5)


@pytest.mark.parametrize("address,family,docker,k3s", [
    ("192.0.2.1", 4, False, False), ("2001:db8::1", 6, True, False),
    ("192.0.2.1", 4, False, True),
])
def test_only_exact_generated_runtime_rules_are_identified(address, family, docker, k3s):
    import shlex
    from mlox.servers.ubuntu.firewall_grants import compile_grant_rules, identify_grant_rule

    grant_id = "12a6eb4e0e8d4b878adc59c09d343749"
    for command in compile_grant_rules(grant_id, address, docker=docker, k3s=k3s):
        insert = command.index("-I")
        chain = command[insert + 1]
        rule = shlex.join(("-A", chain, *command[insert + 3:]))
        assert identify_grant_rule(rule, family=family, chain=chain) == grant_id
        assert identify_grant_rule(rule + " -p tcp", family=family, chain=chain) is None
        assert identify_grant_rule(rule.replace("--match-set mlx", "--match-set other"), family=family, chain=chain) is None
        assert identify_grant_rule(rule.replace("-j ACCEPT", "-j DROP").replace("-j RETURN", "-j ACCEPT"), family=family, chain=chain) is None
        assert identify_grant_rule(rule, family=6 if family == 4 else 4, chain=chain) is None


def test_malformed_or_spoofed_comments_are_not_grants():
    from mlox.servers.ubuntu.firewall_grants import identify_grant_rule

    assert identify_grant_rule('-A MLOX-POLICY-IN -m comment --comment "mlox-temp-bad" -j ACCEPT', family=4, chain="MLOX-POLICY-IN") is None
    assert identify_grant_rule('"', family=4, chain="MLOX-POLICY-IN") is None
    with pytest.raises(ValueError):
        identify_grant_rule("", family=4, chain="INPUT")


def test_ubuntu_grants_use_the_observed_session_and_report_host_expiry():
    from contextlib import nullcontext
    from types import SimpleNamespace
    from unittest.mock import Mock
    from mlox.servers.ubuntu.native import UbuntuNativeServer

    server = UbuntuNativeServer.__new__(UbuntuNativeServer)
    connection = SimpleNamespace(run=Mock(return_value=SimpleNamespace(stdout="192.0.2.42 41234 198.51.100.3 22")))
    server.get_server_connection = Mock(return_value=nullcontext(connection))
    ident = "12a6eb4e0e8d4b878adc59c09d343749"
    server.exec = SimpleNamespace(firewall_status=Mock(return_value="Status: active"), execute=Mock(
        return_value=f"MLOX_GRANT {ident} 192.0.2.42 1800000000\n"))
    grant = server.firewall_grant_current_client(ident, 900)
    assert (grant.grant_id, grant.address, int(grant.expires_at.timestamp())) == (ident, "192.0.2.42", 1800000000)
    assert "192.0.2.42" in server.exec.execute.call_args.args[1]
    assert server.exec.execute.call_args.kwargs["sudo"] is True


def test_ubuntu_skips_inactive_firewall_without_opening_a_grant():
    from contextlib import nullcontext
    from types import SimpleNamespace
    from unittest.mock import Mock
    from mlox.servers.ubuntu.native import UbuntuNativeServer

    server = UbuntuNativeServer.__new__(UbuntuNativeServer)
    connection = SimpleNamespace(run=Mock())
    server.get_server_connection = Mock(return_value=nullcontext(connection))
    server.exec = SimpleNamespace(firewall_status=Mock(return_value="Status: inactive"), execute=Mock())
    assert server.firewall_grant_current_client("12a6eb4e0e8d4b878adc59c09d343749", 900) is None
    connection.run.assert_not_called()
    server.exec.execute.assert_not_called()
