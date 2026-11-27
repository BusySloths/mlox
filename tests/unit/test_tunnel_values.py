import pytest

from mlox.tunnel import TunnelBinding, TunnelEndpoint, TunnelPlan


def test_composite_plan_can_reference_different_servers():
    postgres = TunnelEndpoint("pg", "database", "server-1", "127.0.0.1", 5432, "postgres")
    storage = TunnelEndpoint("s3", "api", "server-2", "127.0.0.1", 9000, "https")
    plan = TunnelPlan("ducklake", (postgres, storage))
    assert [endpoint.server_uuid for endpoint in plan.endpoints] == ["server-1", "server-2"]
    assert TunnelBinding(postgres, 15432).local_host == "127.0.0.1"


def test_plan_rejects_ambiguous_or_invalid_endpoints():
    endpoint = TunnelEndpoint("pg", "database", "server", "127.0.0.1", 5432)
    with pytest.raises(ValueError, match="unique"):
        TunnelPlan("ducklake", (endpoint, endpoint))
    with pytest.raises(ValueError, match="port"):
        TunnelEndpoint("pg", "database", "server", "127.0.0.1", 0)
    with pytest.raises(ValueError, match="loopback"):
        TunnelBinding(endpoint, 15432, "0.0.0.0")
