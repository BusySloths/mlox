from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from mlox.application.use_cases.firewall_grants import grant_current_computer, remove_computer_grant
from mlox.firewall_grants import FirewallAccessGrant
from mlox.server import ServerCapability


def test_grants_are_requested_on_every_firewall_server_and_partial_failures_reported():
    calls = []
    expiry = datetime.now(timezone.utc) + timedelta(minutes=15)

    def success(grant_id, duration):
        calls.append((grant_id, duration))
        return FirewallAccessGrant(grant_id, "192.0.2.1", expiry)

    def fail(grant_id, duration):
        raise RuntimeError("unreachable")

    def bundle(name, action, capabilities={ServerCapability.FIREWALL}):
        return SimpleNamespace(name=name, server=SimpleNamespace(capabilities=capabilities, firewall_grant_current_client=action))

    infra = SimpleNamespace(bundles=[bundle("one", success), bundle("two", lambda *_: None),
                                    bundle("three", fail), bundle("connector", fail, set())])
    result = grant_current_computer(infra, grant_id="12a6eb4e-0e8d-4b87-8adc-59c09d343749", duration_seconds=900)
    assert not result.success
    assert [(row["server"], row["status"]) for row in result.data["servers"]] == [
        ("one", "added"), ("two", "skipped"), ("three", "failed")]
    assert calls == [("12a6eb4e0e8d4b878adc59c09d343749", 900)]


def test_invalid_grants_fail_before_contacting_servers():
    infra = SimpleNamespace(bundles=[])
    assert not grant_current_computer(infra, grant_id="bad", duration_seconds=900).success
    assert not grant_current_computer(infra, grant_id="12a6eb4e0e8d4b878adc59c09d343749", duration_seconds=0).success


def test_remove_targets_only_the_given_grant_and_reports_errors():
    calls = []
    def remove(grant_id):
        calls.append(grant_id)
    def fail(grant_id):
        raise RuntimeError("offline")
    infra = SimpleNamespace(bundles=[
        SimpleNamespace(name="one", server=SimpleNamespace(capabilities={ServerCapability.FIREWALL}, firewall_remove_client_grant=remove)),
        SimpleNamespace(name="two", server=SimpleNamespace(capabilities={ServerCapability.FIREWALL}, firewall_remove_client_grant=fail)),
    ])
    result = remove_computer_grant(infra, grant_id="12a6eb4e-0e8d-4b87-8adc-59c09d343749")
    assert not result.success
    assert calls == ["12a6eb4e0e8d4b878adc59c09d343749"]
    assert [row["status"] for row in result.data["servers"]] == ["removed", "failed"]
