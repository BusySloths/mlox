"""K3s host firewall integration tests on the disposable Multipass guest.

Run on a Multipass-capable host with network access using::

    uv run pytest tests/integration/test_k3s_firewall.py --run-integration -v
"""

import time
import uuid

import pytest

from mlox.firewall import FirewallPolicy
from mlox.servers.ubuntu.firewall_grants import render_grant_mutation
from tests.integration.test_ubuntu_firewall import (
    FirewallGuest,
    NetworkProbe,
    V4_HOST,
    V4_OTHER,
    V4_TRUSTED,
    _sudo,
    network_probe,
)

pytestmark = [pytest.mark.integration, pytest.mark.kubernetes]


@pytest.fixture
def firewall_guest(ubuntu_k3s_server):
    return FirewallGuest(ubuntu_k3s_server, None, "k3s-firewall-test", False)


def test_nodeport_ingress_and_cluster_network_survive_policy(network_probe: NetworkProbe):
    server = network_probe.guest.server
    name = f"mlox-fw-{uuid.uuid4().hex[:8]}"
    grant_id = uuid.uuid4().hex
    with server.get_server_connection() as conn:
        try:
            # The K3s server fixture runs setup, which must install ipset.
            assert _sudo(conn, ["sh", "-c", "command -v ipset"])
            _sudo(conn, ["kubectl", "run", name, "--image=nginx:alpine", "--port=80"])
            _sudo(conn, ["kubectl", "expose", "pod", name, "--type=NodePort", "--port=80"])
            _sudo(conn, ["kubectl", "wait", "--for=condition=Ready", f"pod/{name}", "--timeout=180s"], timeout=200)
            port = int(_sudo(conn, ["kubectl", "get", "service", name, "-o", "jsonpath={.spec.ports[0].nodePort}"]))
            deadline = time.monotonic() + 60
            while network_probe.probe(conn, V4_OTHER, V4_HOST, port) != "open":
                if time.monotonic() >= deadline:
                    pytest.fail("NodePort did not become reachable before applying the policy")
                time.sleep(2)

            policy = FirewallPolicy((int(server.port), 80, 443), (V4_TRUSTED,))
            server.firewall_apply_policy(policy)
            assert server.firewall_status().active is True
            assert not server.firewall_status().error
            assert network_probe.probe(conn, V4_OTHER, V4_HOST, port) == "timeout"
            assert network_probe.probe(conn, V4_TRUSTED, V4_HOST, port) == "open"
            grant = render_grant_mutation(grant_id, address=V4_OTHER, duration_seconds=120, docker=False, k3s=True)
            _sudo(conn, ["sh", "-c", grant])
            assert network_probe.probe(conn, V4_OTHER, V4_HOST, port) == "open"
            server.firewall_apply_policy(policy)
            assert network_probe.probe(conn, V4_OTHER, V4_HOST, port) == "open"
            _sudo(conn, ["kubectl", "get", "nodes"])
            server.firewall_persist_policy(policy)
            assert server.firewall_status().persistence == "enabled"
            revoke = render_grant_mutation(grant_id, address=None, duration_seconds=None, docker=False, k3s=True)
            _sudo(conn, ["sh", "-c", revoke])
            assert network_probe.probe(conn, V4_OTHER, V4_HOST, port) == "timeout"
        finally:
            server.firewall_down()
            conn.sudo(f"kubectl delete service,pod {name} --ignore-not-found --wait=false", hide=True, warn=True, pty=False)
