from contextlib import contextmanager

import pytest

from mlox.ui.registry import clear_handlers, get_handler
from mlox.ui import registry as ui_registry
from mlox.view import services as streamlit_services
from mlox.view.services import registry as registry_view
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


def test_registry_streamlit_settings_handler_is_registered(monkeypatch):
    clear_handlers(bootstrapped=True)
    monkeypatch.setattr(streamlit_services, "_REGISTERED", False)

    streamlit_services.register_builtin_streamlit_services()

    handler = get_handler(
        config_id="registry-3-docker",
        frontend="streamlit",
        function_name="settings",
    )
    assert callable(handler)

    secret_manager_handler = get_handler(
        config_id="openbao-docker",
        frontend="streamlit",
        function_name="settings",
    )
    assert callable(secret_manager_handler)
    assert secret_manager_handler.is_secret_manager_settings

    clear_handlers()


def test_ui_registry_retries_after_failed_bootstrap(monkeypatch):
    calls = []

    class _Module:
        def __init__(self, name):
            self.name = name

        def register_builtin_streamlit_services(self):
            calls.append(self.name)

        def register_builtin_streamlit_servers(self):
            calls.append(self.name)

        def register_builtin_tui_services(self):
            calls.append(self.name)

    def fake_import_module(name):
        if name == "mlox.view.servers.ubuntu" and len(calls) < 2:
            raise RuntimeError("temporary import failure")
        return _Module(name)

    clear_handlers()
    monkeypatch.setattr(ui_registry.importlib, "import_module", fake_import_module)

    assert get_handler(config_id="missing", frontend="streamlit", function_name="setup") is None
    assert ui_registry._BOOTSTRAPPED is False

    assert get_handler(config_id="missing", frontend="streamlit", function_name="setup") is None
    assert ui_registry._BOOTSTRAPPED is True

    clear_handlers()


def test_list_registry_images_fetches_catalog_and_tags(monkeypatch):
    session = _FakeRegistrySession(
        {
            "https://registry.test/v2/_catalog": {
                "repositories": ["team/app", "base/python"]
            },
            "https://registry.test/v2/team/app/tags/list": {
                "name": "team/app",
                "tags": ["latest", "1.0.0"],
            },
            "https://registry.test/v2/base/python/tags/list": {
                "name": "base/python",
                "tags": ["3.12"],
            },
        }
    )

    @contextmanager
    def fake_registry_session(username, password, certificate):
        assert username == "alice"
        assert password == "secret"
        assert certificate == "CERT"
        yield session

    monkeypatch.setattr(registry_view, "_registry_session", fake_registry_session)

    images = registry_view.list_registry_images(
        registry_url="https://registry.test",
        username="alice",
        password="secret",
        certificate="CERT",
    )

    assert [image.repository for image in images] == ["base/python", "team/app"]
    assert images[0].tags == ["3.12"]
    assert images[1].tags == ["1.0.0", "latest"]


def test_list_registry_images_rejects_malformed_catalog(monkeypatch):
    session = _FakeRegistrySession(
        {"https://registry.test/v2/_catalog": {"repositories": "team/app"}}
    )

    @contextmanager
    def fake_registry_session(username, password, certificate):
        yield session

    monkeypatch.setattr(registry_view, "_registry_session", fake_registry_session)

    with pytest.raises(ValueError, match="repository list"):
        registry_view.list_registry_images(
            registry_url="https://registry.test",
            username="alice",
            password="secret",
        )


class _FakeRegistrySession:
    def __init__(self, payloads):
        self.payloads = payloads

    def get(self, url, timeout):
        return _FakeRegistryResponse(self.payloads[url])


class _FakeRegistryResponse:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload
