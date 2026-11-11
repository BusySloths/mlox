import pytest

from mlox.ui.registry import clear_handlers, get_handler
from mlox.ui import registry as ui_registry
from mlox.tui import services as tui_services
from mlox.services.registry.docker import RegistryDockerService


def test_generate_htpasswd_entry_valid():
    entry = RegistryDockerService._generate_htpasswd_entry("alice", "secret")
    assert entry.startswith("alice:")

    username, hashed = entry.strip().split(":", 1)
    assert username == "alice"
    assert hashed.startswith("$2b$")  # bcrypt hash prefix


@pytest.mark.parametrize(
    "username,password",
    [("", "secret"), ("alice", ""), ("", "")],
)
def test_generate_htpasswd_entry_requires_credentials(username, password):
    with pytest.raises(ValueError):
        RegistryDockerService._generate_htpasswd_entry(username, password)


def test_openbao_tui_settings_handler_is_registered(monkeypatch):
    clear_handlers(bootstrapped=True)
    monkeypatch.setattr(tui_services, "_REGISTERED", False)

    tui_services.register_builtin_tui_services()

    handler = get_handler(
        config_id="openbao-docker",
        frontend="tui",
        function_name="settings",
    )
    assert callable(handler)

    clear_handlers()


def test_mlflow_gateway_tui_settings_handlers_are_registered(monkeypatch):
    clear_handlers(bootstrapped=True)
    monkeypatch.setattr(tui_services, "_REGISTERED", False)

    tui_services.register_builtin_tui_services()

    for config_id in (
        "mlflow-gateway-3.8.1-docker",
        "mlflow-gateway-3.8.1-k3s",
        "mlflow-gateway-3.8.1-k3s-managed-tls",
    ):
        handler = get_handler(
            config_id=config_id,
            frontend="tui",
            function_name="settings",
        )
        assert callable(handler)

    clear_handlers()


def test_ui_registry_retries_after_failed_bootstrap(monkeypatch):
    calls = []

    class _Module:
        def __init__(self, name):
            self.name = name

        def register_builtin_tui_services(self):
            calls.append(self.name)

        def register_builtin_tui_servers(self):
            calls.append(self.name)

    def fake_import_module(name):
        if name == "mlox.tui.servers" and len(calls) < 2:
            raise RuntimeError("temporary import failure")
        return _Module(name)

    clear_handlers()
    monkeypatch.setattr(ui_registry.importlib, "import_module", fake_import_module)

    assert get_handler(config_id="missing", frontend="tui", function_name="setup") is None
    assert ui_registry._BOOTSTRAPPED is False

    assert get_handler(config_id="missing", frontend="tui", function_name="setup") is None
    assert ui_registry._BOOTSTRAPPED is True

    clear_handlers()
