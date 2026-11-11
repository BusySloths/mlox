from mlox.config import get_stacks_path, load_config
from mlox.infra import Infrastructure
from mlox.ui.registry import clear_handlers
from legacy.ui.view.servers import connector as connector_view


def test_connector_server_has_streamlit_setup_handler(monkeypatch):
    clear_handlers(bootstrapped=True)
    monkeypatch.setattr(connector_view, "_REGISTERED", False)
    connector_view.register_builtin_streamlit_servers()
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
