import pytest
import yaml
import os
import importlib

from mlox.config import (
    ServiceConfig,
    BuildConfig,
    load_config,
    load_all_service_configs,
)
from mlox.service import AbstractService
from mlox.infra import Infrastructure, Bundle


# Dummy Service Implementation for testing
class DummyService(AbstractService):
    def __init__(
        self,
        name,
        service_config_id,
        template,
        target_path,
        custom_param=None,
        port=None,
    ):
        super().__init__(
            name=name,
            service_config_id=service_config_id,
            template=template,
            target_path=target_path,
        )
        self.custom_param = custom_param
        self.port = port

    def setup(self, conn):
        pass

    def teardown(self, conn):
        pass

    def check(self, conn):
        return {}

    def get_secrets(self) -> dict:
        return {"dummy_secret": {"key": "value"}}


# Dummy UI functions for testing
def dummy_settings_func(
    infra: Infrastructure, bundle: Bundle, service: AbstractService
):
    return {"ui_param_settings": "settings_value"}


def dummy_setup_func(infra: Infrastructure, config: ServiceConfig):
    return {"ui_param_setup": "setup_value"}


@pytest.fixture
def mock_dummy_modules(monkeypatch):
    class MockServiceModule:
        DummyService = DummyService

    class MockUiModule:
        dummy_settings_func = staticmethod(dummy_settings_func)
        dummy_setup_func = staticmethod(dummy_setup_func)

    def mock_import_module(name):
        if name == "dummy.services":
            return MockServiceModule()
        if name == "dummy.ui":
            return MockUiModule()
        return importlib.__import__(name, fromlist=["object"])

    monkeypatch.setattr(importlib, "import_module", mock_import_module)


@pytest.fixture
def mock_package_resources(monkeypatch, tmp_path):
    """
    Mocks `importlib.resources.files` to redirect lookups for 'mlox.services'
    to a temporary directory managed by pytest. This allows testing of
    package data loading functions without a full package installation.
    """
    from importlib import resources

    original_files = resources.files

    def mock_files(package):
        if package == "mlox.services":
            return tmp_path
        if package.startswith("mlox.services."):
            # e.g., 'mlox.services.dummy' -> 'dummy'
            sub_path = package.replace("mlox.services.", "").replace(".", os.path.sep)
            return tmp_path / sub_path
        return original_files(package)

    monkeypatch.setattr(resources, "files", mock_files)


@pytest.fixture
def service_config_data():
    return {
        "id": "test-config-id",
        "name": "TestService",
        "version": "1.0",
        "maintainer": "tester",
        "description": "A test service.",
        "description_short": "Test service.",
        "links": {"docs": "http://example.com/docs"},
        "build": {
            "class_name": "dummy.services.DummyService",
            "params": {
                "name": "TestService",
                "template": "${MLOX_STACKS_PATH}/dummy/template.yaml",
                "target_path": "/opt/${MLOX_USER}/app",
                "port": "${MLOX_AUTO_PORT_HTTP}",
                "custom_param": "build_value",
            },
        },
        "ports": {"http": 8080},
        "ui": {"settings": "dummy.ui.dummy_settings_func"},
    }


def create_yaml_file(tmp_path, name, content, prefix="mlox"):
    service_dir = tmp_path / name
    service_dir.mkdir()
    file_path = service_dir / f"{prefix}.{name}.v1.yaml"
    with open(file_path, "w") as f:
        yaml.dump(content, f)
    return file_path


class TestServiceConfig:
    def test_load_and_instantiate_service(
        self,
        tmp_path,
        service_config_data,
        mock_dummy_modules,
        mock_package_resources,
    ):
        create_yaml_file(tmp_path, "dummy", service_config_data)
        configs = load_all_service_configs()
        assert len(configs) == 1
        config = configs[0]

        assert isinstance(config, ServiceConfig)
        assert config.name == "TestService"

        params = {
            "${MLOX_STACKS_PATH}": "/stacks",
            "${MLOX_USER}": "testuser",
            "${MLOX_AUTO_PORT_HTTP}": "9090",
        }
        service = config.instantiate_service(params)

        assert isinstance(service, DummyService)
        assert service.template == "/stacks/dummy/template.yaml"
        assert service.port == "9090"

    def test_load_all_service_configs(
        self, tmp_path, service_config_data, mock_package_resources
    ):
        create_yaml_file(tmp_path, "dummy1", service_config_data)
        service_config_data["name"] = "TestService2"
        create_yaml_file(tmp_path, "dummy2", service_config_data)

        configs = load_all_service_configs()
        assert len(configs) == 2
        assert {c.name for c in configs} == {"TestService", "TestService2"}

    def test_instantiate_ui(self, service_config_data, mock_dummy_modules):
        config = ServiceConfig(
            build=BuildConfig(**service_config_data.pop("build")), **service_config_data
        )

        settings_func = config.instantiate_ui("settings")
        assert callable(settings_func)
        assert settings_func(None, None, None) == {
            "ui_param_settings": "settings_value"
        }

        none_func = config.instantiate_ui("non_existent")
        assert none_func is None

    def test_load_config_failures(
        self, tmp_path, caplog, mock_package_resources, service_config_data
    ):
        # Create a file with invalid YAML syntax
        service_dir = tmp_path / "invalid"
        service_dir.mkdir()
        file_path = service_dir / "mlox.invalid.v1.yaml"
        with open(file_path, "w") as f:
            f.write("name: Test\n  bad_indent: here")

        # Create a valid file to ensure the loading process continues
        create_yaml_file(tmp_path, "valid", service_config_data)

        # Attempt to load all configs
        configs = load_all_service_configs()

        # Check that only the valid config was loaded and an error was logged
        assert len(configs) == 1
        assert configs[0].name == "TestService"
        assert "Error parsing YAML file" in caplog.text
        assert "mlox.invalid.v1.yaml" in caplog.text
