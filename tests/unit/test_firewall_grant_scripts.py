"""Exercise generated scripts against fake firewall commands, never the host firewall."""

import json
import os
from pathlib import Path
import subprocess

import pytest

from mlox.servers.ubuntu.firewall_grants import grant_set_name, render_grant_mutation


FAKE_FIREWALL = r'''#!/usr/bin/env python3
import json, os, sys
from pathlib import Path
p = Path(os.environ["FAKE_FIREWALL_STATE"])
state = json.loads(p.read_text()) if p.exists() else {"sets": {}, "rules": []}
args = sys.argv[1:]
tool = Path(sys.argv[0]).name
code = 0
if tool == "ipset":
    action, name, *rest = args
    sets = state["sets"]
    if action == "list": code = 0 if name in sets else 1
    elif action == "test": code = 0 if name in sets and any(item[0] == rest[0] for item in sets[name]) else 1
    elif action == "create":
        if name in sets: code = 1
        else: sets[name] = []
    elif action == "add": sets[name].append(rest)
    elif action == "flush": sets[name] = []
    elif action == "destroy": del sets[name]
else:
    if "-S" in args:
        index = args.index("-S")
        chain = args[index + 1]
        for rule in state["rules"]:
            if rule[:index + 2] == [tool, *args[:index], chain]:
                print(" ".join(["-A", chain, *rule[index + 2:]]))
        sys.exit(0)
    index = next((i for i, arg in enumerate(args) if arg in ("-C", "-I", "-D")), None)
    action, chain = args[index:index+2]
    rule = [tool, *args[:index], chain, *args[index+2:]]
    if action == "-I":
        rule.pop(index + 2)  # insertion position
        if os.environ.get("FAIL_DOCKER_INSERT") and chain == "MLOX-POLICY-DOCKER": code = 1
        else: state["rules"].append(rule)
    elif action == "-C":
        if chain in ("INPUT", "DOCKER-USER", "PREROUTING"): code = 0
        elif rule not in state["rules"]: code = 1
    elif rule in state["rules"]: state["rules"].remove(rule)
    else: code = 1
p.write_text(json.dumps(state))
sys.exit(code)
'''


@pytest.fixture
def host(tmp_path):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    executable = bin_dir / "fake"
    executable.write_text(FAKE_FIREWALL)
    executable.chmod(0o755)
    for name in ("ipset", "iptables", "ip6tables"):
        (bin_dir / name).symlink_to(executable)
    (tmp_path / "lock").mkdir()
    env = dict(os.environ, PATH=f"{bin_dir}:{os.environ['PATH']}", FAKE_FIREWALL_STATE=str(tmp_path / "state.json"))

    def run(grant, address=None, duration=None, *, docker=False, k3s=False, fail=False):
        script = render_grant_mutation(grant, address=address, duration_seconds=duration, docker=docker, k3s=k3s)
        script = script.replace("/run/lock/", str(tmp_path / "lock") + "/")
        script = script.replace("/run/mlox-firewall-grants", str(tmp_path / "grants"))
        return subprocess.run(["sh", "-c", script], env=dict(env, FAIL_DOCKER_INSERT="1" if fail else ""), capture_output=True, text=True)

    def state():
        return json.loads((tmp_path / "state.json").read_text())

    return tmp_path, run, state


def test_shared_ip_grants_are_independent_and_revocation_removes_only_one(host):
    _, run, state = host
    first = "12a6eb4e0e8d4b878adc59c09d343749"
    second = "22a6eb4e0e8d4b878adc59c09d343749"
    assert run(first, "192.0.2.1", 900, docker=True).returncode == 0
    assert run(second, "192.0.2.1", 3600, docker=True).returncode == 0
    assert state()["sets"][grant_set_name(first, 4)] == [["192.0.2.1", "timeout", "900"]]
    assert run(first, docker=True).returncode == 0
    assert grant_set_name(first, 4) not in state()["sets"]
    assert state()["sets"][grant_set_name(second, 4)] == [["192.0.2.1", "timeout", "3600"]]
    assert all(first not in " ".join(rule) for rule in state()["rules"])


def test_renewal_replaces_old_family_and_failed_add_is_closed(host):
    root, run, state = host
    grant = "12a6eb4e0e8d4b878adc59c09d343749"
    assert run(grant, "192.0.2.1", 900, docker=True).returncode == 0
    assert run(grant, "2001:db8::1", 900, docker=True).returncode == 0
    assert grant_set_name(grant, 4) not in state()["sets"]
    assert run(grant, "192.0.2.2", 900, docker=True, fail=True).returncode != 0
    assert state()["sets"][grant_set_name(grant, 4)] == []
    assert not (root / "grants" / f"{grant}.grant").exists()


def test_collision_does_not_change_existing_grant(host):
    _, run, state = host
    first = "12a6eb4e0e8d4b878adc59c000000000"
    second = "12a6eb4e0e8d4b878adc59c0ffffffff"
    assert run(first, "192.0.2.1", 900).returncode == 0
    before = state()
    assert run(second, "192.0.2.2", 900).returncode != 0
    assert state() == before


def test_k3s_grant_adds_and_removes_the_pre_dnat_rule(host):
    _, run, state = host
    grant = "12a6eb4e0e8d4b878adc59c09d343749"
    assert run(grant, "2001:db8::1", 900, k3s=True).returncode == 0
    rules = state()["rules"]
    assert len(rules) == 2
    assert any(rule[:4] == ["ip6tables", "-t", "mangle", "MLOX-INGRESS"] for rule in rules)
    assert run(grant, k3s=True).returncode == 0
    assert not state()["rules"]


def test_grant_script_rejects_invalid_inputs():
    grant = "12a6eb4e0e8d4b878adc59c09d343749"
    for address, duration in [("127.0.0.1", 900), ("192.0.2.1; touch /tmp/x", 900), ("192.0.2.1", 0), (None, 10)]:
        with pytest.raises(ValueError):
            render_grant_mutation(grant, address=address, duration_seconds=duration, docker=False, k3s=False)
    with pytest.raises(ValueError):
        render_grant_mutation(grant, address="192.0.2.1", duration_seconds=900, docker=True, k3s=True)


def test_policy_replay_and_count_accept_only_owned_grant_rules(host):
    from mlox.execution.firewall_policy import _TEMP_RULES_PROGRAM

    root, run, state = host
    grant = "12a6eb4e0e8d4b878adc59c09d343749"
    assert run(grant, "192.0.2.1", 900).returncode == 0
    program = _TEMP_RULES_PROGRAM.replace('"/run/mlox-firewall-grants"', repr(str(root / "grants")))
    env = dict(os.environ, PATH=f"{root / 'bin'}:{os.environ['PATH']}", FAKE_FIREWALL_STATE=str(root / "state.json"))
    def check(mode):
        return subprocess.run(["python3", "-c", program, "iptables", "", "MLOX-POLICY-IN", mode], env=env, capture_output=True, text=True, check=True).stdout.strip()
    assert check("count") == "0"
    assert check("restore").startswith("-I MLOX-POLICY-IN 1 -m set")
    (root / "grants" / (grant_set_name(grant, 4) + ".owner")).write_text("other")
    assert check("count") == "1"
    assert check("restore") == ""


def test_listing_omits_removed_and_expired_sets(host):
    from mlox.servers.ubuntu.firewall_grants import _LIST_GRANTS_PROGRAM, parse_grant_listing

    root, run, state = host
    grant = "12a6eb4e0e8d4b878adc59c09d343749"
    assert run(grant, "192.0.2.1", 900).returncode == 0
    program = _LIST_GRANTS_PROGRAM.replace('"/run/mlox-firewall-grants"', repr(str(root / "grants")))
    env = dict(os.environ, PATH=f"{root / 'bin'}:{os.environ['PATH']}", FAKE_FIREWALL_STATE=str(root / "state.json"))
    def listing():
        output = subprocess.run(["python3", "-c", program], env=env, capture_output=True, text=True, check=True).stdout
        return parse_grant_listing(output)
    assert [(item.grant_id, item.address) for item in listing()] == [(grant, "192.0.2.1")]
    raw = state()
    raw["sets"][grant_set_name(grant, 4)] = []  # Simulate kernel timeout.
    (root / "state.json").write_text(json.dumps(raw))
    assert listing() == ()
