import pytest
import yaml
import os
import importlib
from importlib import metadata as importlib_metadata

from mlox.config import (
    ServiceConfig,
    BuildConfig,
    load_config,
    load_all_service_configs,
)
from mlox.service import AbstractService
from mlox.infra import Infrastructure, Bundle
from mlox.ui.registry import clear_handlers, register


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

    def mock_import_module(name):
        if name == "dummy.services":
            return MockServiceModule()
        return importlib.__import__(name, fromlist=["object"])

    monkeypatch.setattr(importlib, "import_module", mock_import_module)


@pytest.fixture
def mock_dummy_ui_registry():
    clear_handlers(bootstrapped=True)
    register(
        config_id="test-config-id",
        frontend="streamlit",
        function_name="settings",
        handler=dummy_settings_func,
    )
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

    class _NoEntryPoints:
        def select(self, *, group):
            return []

    monkeypatch.setattr(resources, "files", mock_files)
    monkeypatch.setattr(importlib_metadata, "entry_points", lambda: _NoEntryPoints())


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

    def test_get_ui_handler(
        self, service_config_data, mock_dummy_modules, mock_dummy_ui_registry
    ):
        config = ServiceConfig(
            build=BuildConfig(**service_config_data.pop("build")), **service_config_data
        )

        settings_func = config.get_ui_handler("streamlit", "settings")
        assert callable(settings_func)
        assert settings_func(None, None, None) == {
            "ui_param_settings": "settings_value"
        }

        none_func = config.get_ui_handler("streamlit", "non_existent")
        assert none_func is None

    def test_service_config_accepts_capabilities(self, service_config_data):
        service_config_data["build"] = BuildConfig(**service_config_data["build"])
        service_config_data["capabilities"] = {
            "service": ["repository"],
            "backend": ["docker"],
        }
        config = ServiceConfig(**service_config_data)

        assert config.declared_capabilities()["service"] == {"repository"}
        assert config.backend_capabilities() == {"docker"}

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


def test_service_capabilities_fall_back_from_groups(service_config_data):
    service_config_data["build"] = BuildConfig(**service_config_data["build"])
    service_config_data["groups"] = {
        "service": None,
        "model-registry": None,
        "backend": {"docker": None},
    }
    config = ServiceConfig(**service_config_data)

    assert config.service_capabilities() == {"model_registry"}
    assert config.backend_capabilities() == {"docker"}


def test_service_capability_mismatch_logs_warning(
    tmp_path, caplog, mock_dummy_modules, service_config_data
):
    service_config_data["capabilities"] = {
        "service": ["repository"],
        "backend": ["docker"],
    }
    create_yaml_file(tmp_path, "dummy", service_config_data)

    caplog.set_level("WARNING")
    config = load_config(str(tmp_path), "dummy", "mlox.dummy.v1.yaml")

    assert config is not None
    assert "declares service capabilities not supported" in caplog.text
    assert "does not implement AbstractRepositoryService" in caplog.text


def test_builtin_service_configs_have_matching_explicit_capabilities():
    from mlox.config import _load_build_class
    from mlox.service import ServiceCapability

    configs = load_all_service_configs(include_plugins=False)
    known = {capability.value for capability in ServiceCapability}
    assert configs

    for config in configs:
        assert config.capabilities, config.path
        assert config.service_capabilities(), config.path
        assert config.backend_capabilities(), config.path
        assert config.service_capabilities() <= known, config.path

        service_class = _load_build_class(config)
        assert service_class is not None, config.path
        class_capabilities = {
            capability.value if hasattr(capability, "value") else str(capability)
            for capability in getattr(service_class, "capabilities", set())
        }
        assert config.service_capabilities() <= class_capabilities, config.path


def test_builtin_web_ui_service_configs_advertise_web_ui_capability():
    configs = {
        config.id: config for config in load_all_service_configs(include_plugins=False)
    }
    web_ui_config_ids = {
        "airflow-2.9.2-docker",
        "airflow-3.1.3-docker",
        "headlamp-newest-k3s",
        "k8s-dashboard-newest-k3s",
        "kubeapps-newest-k3s",
        "kubeflow-1.10.1-k3s",
        "litellm-ollama-1.77.7-docker",
        "minio-release-2025-07-23-docker",
        "mlflow-2.22.0-docker",
        "mlflow-3.8.1-docker",
        "openbao-docker",
    }

    assert web_ui_config_ids <= set(configs)
    for config_id in web_ui_config_ids:
        assert "web_ui" in configs[config_id].service_capabilities()


def test_dev_terminal_supports_kubernetes_agent_backends():
    configs = {
        config.id: config for config in load_all_service_configs(include_plugins=False)
    }

    config = configs["dev-terminal-0.1-beta"]

    assert config.backend_capabilities() == {
        "native",
        "docker",
        "kubernetes",
        "kubernetes_agent",
        "k3s_agent",
    }
    assert set(config.groups["backend"]) == {
        "native",
        "docker",
        "kubernetes",
        "kubernetes-agent",
        "k3s-agent",
    }


@pytest.mark.parametrize(
    "config_id",
    [
        "gcp-bigquery-0.1.0",
        "gcp-secret-manager-0.1.0",
        "gcp-sheets-0.1.0",
        "gcp-storage-0.1.0",
    ],
)
def test_externally_hosted_gcp_services_use_connector_backend(config_id):
    configs = {
        config.id: config for config in load_all_service_configs(include_plugins=False)
    }

    config = configs[config_id]

    assert config.backend_capabilities() == {"connector"}
    assert set(config.groups["backend"]) == {"connector"}
    assert config.requirements == {
        "cpus": 0.0,
        "ram_gb": 0.0,
        "disk_gb": 0.0,
    }
