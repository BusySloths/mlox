import pytest
import yaml
import os
import importlib

from mlox.config import (
    ServiceConfig,
    BuildConfig,
    load_config,
    load_all_server_configs,
)
from mlox.server import AbstractServer
from mlox.infra import Infrastructure


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


# Dummy UI functions for testing
def dummy_setup_func(infra: Infrastructure, config: ServiceConfig):
    return {"ui_param_setup": "setup_value"}


@pytest.fixture
def mock_dummy_modules(monkeypatch):
    class MockServerModule:
        DummyServer = DummyServer

    class MockUiModule:
        dummy_setup_func = staticmethod(dummy_setup_func)

    def mock_import_module(name):
        if name == "dummy.servers":
            return MockServerModule()
        if name == "dummy.ui":
            return MockUiModule()
        return importlib.__import__(name, fromlist=["object"])

    monkeypatch.setattr(importlib, "import_module", mock_import_module)


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
        "ui": {"setup": "dummy.ui.dummy_setup_func"},
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
        self, tmp_path, server_config_data, mock_dummy_modules
    ):
        create_yaml_file(tmp_path, "dummy", server_config_data)
        config = load_config(tmp_path, "dummy", "mlox-server.dummy.v1.yaml")

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

    def test_load_all_server_configs(self, tmp_path, server_config_data):
        create_yaml_file(tmp_path, "dummy1", server_config_data)
        server_config_data["name"] = "TestServer2"
        create_yaml_file(tmp_path, "dummy2", server_config_data)

        configs = load_all_server_configs(tmp_path)
        assert len(configs) == 2
        assert {c.name for c in configs} == {"TestServer", "TestServer2"}

    def test_instantiate_ui(self, server_config_data, mock_dummy_modules):
        config = ServiceConfig(
            build=BuildConfig(**server_config_data.pop("build")), **server_config_data
        )

        setup_func = config.instantiate_ui("setup")
        assert callable(setup_func)
        assert setup_func(None, None) == {"ui_param_setup": "setup_value"}

        none_func = config.instantiate_ui("non_existent")
        assert none_func is None
