from mlox.config import get_stacks_path, load_config
from mlox.application.use_cases import servers
from mlox.infra import Infrastructure
from mlox.project.aggregate import ProjectAggregate
from mlox.server import ServerCapability
from mlox.servers.connector.virtual import VirtualConnectorServer
from mlox.ui.registry import clear_handlers
from mlox.view.servers import connector as connector_view


def make_server() -> VirtualConnectorServer:
    return VirtualConnectorServer(
        ip="mlox-connector-test01",
        root="mlox_connector",
        root_pw="",
        service_config_id="connector-server",
    )


def test_virtual_connector_server_has_no_physical_resources():
    server = make_server()

    assert server.capabilities == {ServerCapability.CONNECTOR}
    assert server.backend == ["connector"]
    assert server.state == "running"
    assert server.test_connection() is True
    assert server.get_server_info() == {
        "host": "mlox-connector-test01",
        "cpu_count": 0,
        "ram_gb": 0.0,
        "storage_gb": 0.0,
        "pretty_name": "Virtual connector backend",
    }


def test_virtual_connection_supports_connector_service_lifecycle_shape():
    server = make_server()

    with server.get_server_connection() as connection:
        assert connection.is_connected is True
        assert connection.run("true").ok is True
        assert connection.run("echo ok").stdout == "ok\n"

    assert connection.is_connected is False


def test_connector_server_config_can_be_added_and_filtered():
    config = load_config(
        get_stacks_path(prefix="mlox-server"),
        "/connector",
        "mlox-server.connector.yaml",
    )
    assert config is not None

    infra = Infrastructure()
    project = ProjectAggregate(name="demo", infrastructure=infra)
    first = servers.add_server(
        project,
        lambda path: config,
        template_path="connector",
        ip="mlox-connector-first",
        port=0,
        root_user="",
        root_password="",
        extra_params={"${MLOX_IP}": "mlox-connector-first"},
    )
    second = servers.add_server(
        project,
        lambda path: config,
        template_path="connector",
        ip="mlox-connector-second",
        port=0,
        root_user="",
        root_password="",
        extra_params={"${MLOX_IP}": "mlox-connector-second"},
    )
    first_bundle = first.data["bundle"]
    second_bundle = second.data["bundle"]

    assert first_bundle is not None
    assert second_bundle is not None
    assert isinstance(first_bundle.server, VirtualConnectorServer)
    assert isinstance(second_bundle.server, VirtualConnectorServer)
    assert infra.filter_bundles_by_backend("connector") == [
        first_bundle,
        second_bundle,
    ]


def test_connector_server_has_streamlit_setup_handler(monkeypatch):
    clear_handlers()
    monkeypatch.setattr(connector_view, "_REGISTERED", False)
    monkeypatch.setattr(
        connector_view.st,
        "text_input",
        lambda *args, **kwargs: "analytics-connectors",
    )

    config = load_config(
        get_stacks_path(prefix="mlox-server"),
        "/connector",
        "mlox-server.connector.yaml",
    )

    assert config is not None
    setup = config.get_ui_handler("streamlit", "setup")
    assert callable(setup)
    assert setup(Infrastructure(), config) == {"${MLOX_IP}": "analytics-connectors"}

    clear_handlers()


def test_connector_backend_lifecycle_is_virtual_and_idempotent():
    server = make_server()

    server.stop_backend_runtime()
    assert server.get_backend_status() == {
        "backend.is_running": False,
        "backend.connector.virtual": True,
    }

    server.start_backend_runtime()
    assert server.get_backend_status()["backend.is_running"] is True

    server.teardown()
    assert server.state == "shutdown"
    server.setup()
    assert server.state == "running"
