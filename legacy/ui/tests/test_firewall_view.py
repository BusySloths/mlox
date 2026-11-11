from types import SimpleNamespace

from mlox.servers.ubuntu.native import UbuntuNativeServer
from legacy.ui.view.servers.ubuntu.native import (
    _collect_firewall_port_rows,
    _collect_firewall_ports,
    _filter_firewall_port_rows,
    _firewall_status_message,
    _is_firewall_up,
    _parse_firewall_open_ports,
)


def test_firewall_port_collection():
    server = UbuntuNativeServer(ip="10.0.0.10", root="root", root_pw="pw", service_config_id="ubuntu-native")

    class DummyService:
        def __init__(self, ports):
            self.service_ports = ports

    bundle = SimpleNamespace(
        services=[
            DummyService({"http": 8080, "grpc": 50051}),
            DummyService({"ui": 8080, "metrics": 9090}),
        ]
    )
    assert _collect_firewall_ports(bundle, server) == [22, 8080, 9090, 50051]
    assert _collect_firewall_port_rows(bundle, server) == [
        {"port_number": 22, "service": "Server", "port_name": "SSH"},
        {"port_number": 8080, "service": "DummyService", "port_name": "http"},
        {"port_number": 8080, "service": "DummyService", "port_name": "ui"},
        {"port_number": 9090, "service": "DummyService", "port_name": "metrics"},
        {"port_number": 50051, "service": "DummyService", "port_name": "grpc"},
    ]


def test_ubuntu_native_firewall_status_parsing_and_filtering():
    status = """Status: active
-N MLOX-FIREWALL
-A MLOX-FIREWALL -p tcp -m tcp --dport 22 -j ACCEPT
-A MLOX-FIREWALL -p tcp -m tcp --dport 8080 -j ACCEPT
-A MLOX-FIREWALL -p tcp -m tcp --dport 9090 -j DROP
-A MLOX-DOCKER-FIREWALL -p tcp -m conntrack --ctorigdstport 50051 -j ACCEPT
"""
    assert _parse_firewall_open_ports(status) == {22, 8080, 50051}
    assert _parse_firewall_open_ports("Status: inactive") == set()
    assert _parse_firewall_open_ports(None) is None

    rows = [
        {"port_number": 22, "service": "Server", "port_name": "SSH"},
        {"port_number": 8080, "service": "api", "port_name": "HTTP"},
    ]
    assert _filter_firewall_port_rows(rows, {22, 8080, 9999}) == [
        {"port_number": 22, "service": "Server", "port_name": "SSH"},
        {"port_number": 8080, "service": "api", "port_name": "HTTP"},
        {"port_number": 9999, "service": "Unknown", "port_name": "iptables rule"},
    ]
    assert _filter_firewall_port_rows(rows, None) == rows
    assert (
        _firewall_status_message("Status: inactive", set(), [])
        == "Firewall is not up. All ports are open."
    )
    assert (
        _firewall_status_message(None, None, rows)
        == "Could not read firewall status. Showing configured ports instead."
    )
    assert _firewall_status_message("Status: active", set(), []) == (
        "No open firewall ports found."
    )
    assert _firewall_status_message("Status: active", {22}, rows) is None
    assert _is_firewall_up("Status: active") is True
    assert _is_firewall_up("Status: inactive") is False
    assert _is_firewall_up(None) is False
