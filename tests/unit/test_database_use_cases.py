from types import SimpleNamespace

from mlox.application.use_cases.databases import describe_databases
from mlox.service import ServiceCapability


def test_describe_databases_lists_only_database_capable_services() -> None:
    database = SimpleNamespace(
        name="postgres",
        service_config_id="mlox.postgres.16",
        state="running",
        capabilities={ServiceCapability.DATABASE},
        db="analytics",
        port=5432,
        service_ports={"Postgres": 5432},
        service_urls={"Postgres": "https://10.0.0.5:5432"},
    )
    monitor = SimpleNamespace(
        name="otel",
        state="running",
        capabilities={ServiceCapability.MONITOR},
    )
    bundle = SimpleNamespace(
        name="prod",
        server=SimpleNamespace(ip="10.0.0.5"),
        services=[monitor, database],
    )
    infra = SimpleNamespace(bundles=[bundle])

    result = describe_databases(infra)

    assert result.success
    assert result.data["rows"] == [
        {
            "bundle": "prod",
            "server": "10.0.0.5",
            "service": "postgres",
            "engine": "postgres",
            "state": "running",
            "database": "analytics",
            "port": "5432",
            "endpoint_count": 1,
            "endpoints": "https://10.0.0.5:5432",
            "bundle_ref": bundle,
            "service_ref": database,
        }
    ]


def test_describe_databases_uses_declared_config_capabilities() -> None:
    database = SimpleNamespace(name="configured-db", capabilities=set())
    bundle = SimpleNamespace(name="dev", server=None, services=[database])
    config = SimpleNamespace(service_capabilities=lambda: {"database"})
    infra = SimpleNamespace(
        bundles=[bundle], get_service_config=lambda service: config
    )

    result = describe_databases(infra)

    assert result.success
    assert result.data["rows"][0]["service"] == "configured-db"
