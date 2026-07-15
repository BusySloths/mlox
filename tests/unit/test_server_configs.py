import pytest
import yaml
import os
import importlib
import logging

from mlox.config import (
    ServiceConfig,
    BuildConfig,
    load_config,
    load_all_server_configs,
)
from mlox.server import (
    AbstractGitServer,
    AbstractNativeServer,
    AbstractServer,
    ServerCapability,
)
from mlox.infra import Infrastructure
from mlox.ui.registry import clear_handlers, get_handler, register


# Dummy Server Implementation for testing
class DummyServer(AbstractServer):
    def __init__(
        self, ip, root, root_pw, service_config_id, port="22", custom_server_param=None
    ):
        super().__init__(
            ip=ip,
            root=root,
            root_pw=root_pw,
            service_config_id=service_config_id,
            port=port,
        )
        self.custom_server_param = custom_server_param

    # Implementing all abstract methods to make it concrete
    def setup(self):
        pass

    def update(self):
        pass

    def teardown(self):
        pass

    def get_server_info(self):
        return {}

    def enable_debug_access(self):
        pass

    def disable_debug_access(self):
        pass

    def setup_backend(self):
        pass

    def teardown_backend(self):
        pass

    def get_backend_status(self):
        return {}

    def start_backend_runtime(self):
        pass

    def stop_backend_runtime(self):
        pass


class CapabilityServer(DummyServer, AbstractGitServer, AbstractNativeServer):
    capabilities = {ServerCapability.GIT, ServerCapability.NATIVE}

    def git_clone(self, repo_url: str, path: str) -> None:
        pass

    def git_pull(self, path: str) -> None:
        pass

    def git_remove(self, path: str) -> None:
        pass


class MissingGitAbcServer(DummyServer):
    capabilities = {ServerCapability.GIT}


# Dummy UI functions for testing
def dummy_setup_func(infra: Infrastructure, config: ServiceConfig):
    return {"ui_param_setup": "setup_value"}


@pytest.fixture
def mock_dummy_modules(monkeypatch):
    class MockServerModule:
        DummyServer = DummyServer
        CapabilityServer = CapabilityServer
        MissingGitAbcServer = MissingGitAbcServer

    def mock_import_module(name):
        if name == "dummy.servers":
            return MockServerModule()
        return importlib.__import__(name, fromlist=["object"])

    monkeypatch.setattr(importlib, "import_module", mock_import_module)


@pytest.fixture
def mock_dummy_ui_registry():
    clear_handlers(bootstrapped=True)
    register(
        config_id="test-config-id",
        frontend="streamlit",
        function_name="setup",
        handler=dummy_setup_func,
    )
    yield
    clear_handlers()


@pytest.fixture
def mock_package_resources(monkeypatch, tmp_path):
    """
    Mocks `importlib.resources.files` to redirect lookups for 'mlox.servers'
    to a temporary directory managed by pytest. This allows testing of
    package data loading functions without a full package installation.
    """
    from importlib import resources

    original_files = resources.files

    def mock_files(package):
        if package == "mlox.servers":
            return tmp_path
        if package.startswith("mlox.servers."):
            # e.g., 'mlox.servers.dummy' -> 'dummy'
            sub_path = package.replace("mlox.servers.", "").replace(".", os.path.sep)
            return tmp_path / sub_path
        return original_files(package)

    monkeypatch.setattr(resources, "files", mock_files)


@pytest.fixture
def server_config_data():
    return {
        "id": "test-config-id",
        "name": "TestServer",
        "version": "24.04",
        "maintainer": "tester",
        "description": "A test server.",
        "description_short": "Test server.",
        "links": {"home": "http://example.com"},
        "build": {
            "class_name": "dummy.servers.DummyServer",
            "params": {
                "ip": "${MLOX_IP}",
                "root": "${MLOX_ROOT}",
                "root_pw": "${MLOX_ROOT_PW}",
                "custom_server_param": "build_value",
            },
        },
    }


def create_yaml_file(tmp_path, name, content, prefix="mlox-server"):
    server_dir = tmp_path / name
    server_dir.mkdir()
    file_path = server_dir / f"{prefix}.{name}.v1.yaml"
    with open(file_path, "w") as f:
        yaml.dump(content, f)
    return file_path


class TestServerConfig:
    def test_load_and_instantiate_server(
        self,
        tmp_path,
        server_config_data,
        mock_dummy_modules,
        mock_package_resources,
    ):
        create_yaml_file(tmp_path, "dummy", server_config_data)

        # Use the load_all_server_configs function, which is known to work with
        # the mocked resources, to get the configuration object for this test.
        configs = load_all_server_configs()
        assert len(configs) == 1
        config = configs[0]

        assert isinstance(config, ServiceConfig)
        assert config.name == "TestServer"

        params = {
            "${MLOX_IP}": "127.0.0.1",
            "${MLOX_ROOT}": "root",
            "${MLOX_ROOT_PW}": "password",
        }
        server = config.instantiate_server(params)

        assert isinstance(server, DummyServer)
        assert server.ip == "127.0.0.1"
        assert server.custom_server_param == "build_value"

    def test_load_all_server_configs(
        self, tmp_path, server_config_data, mock_package_resources
    ):
        create_yaml_file(tmp_path, "dummy1", server_config_data)
        server_config_data["name"] = "TestServer2"
        create_yaml_file(tmp_path, "dummy2", server_config_data)

        configs = load_all_server_configs()
        assert len(configs) == 2
        assert {c.name for c in configs} == {"TestServer", "TestServer2"}

    def test_get_ui_handler(
        self, server_config_data, mock_dummy_modules, mock_dummy_ui_registry
    ):
        config = ServiceConfig(
            build=BuildConfig(**server_config_data.pop("build")), **server_config_data
        )

        setup_func = config.get_ui_handler("streamlit", "setup")
        assert callable(setup_func)
        assert setup_func(None, None) == {"ui_param_setup": "setup_value"}

        none_func = config.get_ui_handler("streamlit", "non_existent")
        assert none_func is None

    def test_capability_helpers_parse_explicit_and_legacy(self, server_config_data):
        explicit_data = dict(server_config_data)
        explicit_data["build"] = BuildConfig(**server_config_data["build"])
        explicit_data["capabilities"] = {
            "server": ["git"],
            "backend": ["kubernetes"],
        }
        explicit = ServiceConfig(**explicit_data)
        assert explicit.server_capabilities() == {"git"}
        assert explicit.backend_capabilities() == {"kubernetes"}

        legacy_data = dict(server_config_data)
        legacy_data["build"] = BuildConfig(**server_config_data["build"])
        legacy_data["groups"] = {
            "server": {"git": None},
            "backend": {"kubernetes": {"k3s": None}},
        }
        legacy = ServiceConfig(**legacy_data)
        assert legacy.server_capabilities() == {"git"}
        assert legacy.backend_capabilities() == {"kubernetes"}

    def test_capability_validation_accepts_matching_config(
        self,
        tmp_path,
        server_config_data,
        mock_dummy_modules,
        mock_package_resources,
        caplog,
    ):
        server_config_data["build"]["class_name"] = "dummy.servers.CapabilityServer"
        server_config_data["capabilities"] = {
            "server": ["git"],
            "backend": ["native"],
        }
        create_yaml_file(tmp_path, "dummy", server_config_data)

        with caplog.at_level(logging.WARNING):
            configs = load_all_server_configs()

        assert len(configs) == 1
        assert "capabilities" not in caplog.text

    def test_capability_validation_warns_and_still_loads(
        self,
        tmp_path,
        server_config_data,
        mock_dummy_modules,
        mock_package_resources,
        caplog,
    ):
        server_config_data["build"]["class_name"] = "dummy.servers.CapabilityServer"
        server_config_data["capabilities"] = {
            "server": ["git", "made_up"],
            "backend": ["docker"],
        }
        create_yaml_file(tmp_path, "dummy", server_config_data)

        with caplog.at_level(logging.WARNING):
            configs = load_all_server_configs()

        assert len(configs) == 1
        assert "unknown capabilities" in caplog.text
        assert "declares capabilities not supported" in caplog.text
        assert "supports capabilities not advertised" in caplog.text

    def test_capability_validation_warns_for_missing_abc(
        self,
        tmp_path,
        server_config_data,
        mock_dummy_modules,
        mock_package_resources,
        caplog,
    ):
        server_config_data["build"]["class_name"] = "dummy.servers.MissingGitAbcServer"
        server_config_data["capabilities"] = {"server": ["git"]}
        create_yaml_file(tmp_path, "dummy", server_config_data)

        with caplog.at_level(logging.WARNING):
            configs = load_all_server_configs()

        assert len(configs) == 1
        assert "does not implement AbstractGitServer" in caplog.text


def test_builtin_server_config_capabilities_match_classes():
    configs = load_all_server_configs(include_plugins=False)
    by_id = {config.id: config for config in configs}
    expected = {
        "local-server": ({"git", "health"}, {"local"}),
        "connector-server": ({"health"}, {"connector"}),
        "ubuntu-simple-24.04-server": ({"terminal"}, {"native"}),
        "ubuntu-native-24.04-server": (
            {"git", "firewall", "initial_auth_password", "terminal"},
            {"native"},
        ),
        "ubuntu-docker-24.04-server": (
            {"git", "firewall", "health", "initial_auth_password", "terminal"},
            {"docker"},
        ),
        "ubuntu-k3s-24.04-server": (
            {"git", "firewall", "health", "initial_auth_password", "terminal"},
            {"kubernetes"},
        ),
        "ubuntu-multipass-native-24.04-server": (
            {"git", "firewall", "initial_auth_password", "terminal"},
            {"native"},
        ),
        "ubuntu-multipass-docker-24.04-server": (
            {"git", "firewall", "health", "initial_auth_password", "terminal"},
            {"docker"},
        ),
        "ubuntu-multipass-k3s-24.04-server": (
            {"git", "firewall", "health", "initial_auth_password", "terminal"},
            {"kubernetes"},
        ),
    }

    for config_id, (server_capabilities, backend_capabilities) in expected.items():
        config = by_id[config_id]
        assert config.server_capabilities() == server_capabilities
        assert config.backend_capabilities() == backend_capabilities
        module_path, class_name = config.build.class_name.rsplit(".", 1)
        server_class = getattr(importlib.import_module(module_path), class_name)
        class_capabilities = {
            (
                capability.value
                if isinstance(capability, ServerCapability)
                else str(capability)
            )
            for capability in server_class.capabilities
        }
        assert (
            config.server_capabilities() | config.backend_capabilities()
            == class_capabilities
        )


def test_builtin_tui_server_setup_handlers_are_registered():
    clear_handlers()
    try:
        expected_config_ids = {
            "local-server",
            "connector-server",
            "ubuntu-simple-24.04-server",
            "ubuntu-native-24.04-server",
            "ubuntu-docker-24.04-server",
            "ubuntu-k3s-24.04-server",
            "ubuntu-multipass-native-24.04-server",
            "ubuntu-multipass-docker-24.04-server",
            "ubuntu-multipass-k3s-24.04-server",
        }

        for config_id in expected_config_ids:
            assert callable(
                get_handler(
                    config_id=config_id,
                    frontend="tui",
                    function_name="setup",
                )
            )
    finally:
        clear_handlers()
