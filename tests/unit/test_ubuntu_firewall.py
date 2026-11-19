from mlox.servers.ubuntu.firewall import parse_firewall_status


def test_ubuntu_status_translates_rules_to_capability_status():
    raw = ("Status: active\nPersistence: enabled\n-N MLOX-POLICY-IN\n"
           "-A MLOX-POLICY-IN -s 192.0.2.8/32 -j ACCEPT\n"
           "-A MLOX-POLICY-IN -p tcp --dport 22 -j ACCEPT\n")
    status = parse_firewall_status(raw)
    assert status.active is True
    assert status.persistence == "enabled"
    assert status.public_ports == (22,)
    assert status.trusted_sources == ("192.0.2.8",)
    assert status.raw == raw


def test_ubuntu_status_reports_missing_or_partial_rules():
    assert parse_firewall_status(None).active is None
    assert parse_firewall_status("unrecognized").active is None
    partial = parse_firewall_status("Status: active\nWarning: policy missing in one address family")
    assert partial.active is True
    assert partial.error


def test_ubuntu_status_recognizes_previous_policy_for_migration():
    status = parse_firewall_status("Status: active\n-N MLOX-FIREWALL\n")
    assert status.previous_policy
