import pytest
import yaml
import os
import importlib
from dataclasses import fields

from mlox.config import (
    ServiceConfig,
    ServerConfig,
    BuildConfig,
    load_service_configs,
    load_all_service_configs,
    load_server_configs,
    load_all_server_configs,
)
from mlox.service import AbstractService
from mlox.server import AbstractServer
from mlox.infra import Infrastructure, Bundle  # For dummy UI functions

# Assuming dummy_conftest.py contains DummyService, DummyServer, dummy_settings_func, dummy_setup_func
# and the pytest fixtures (mock_dummy_service_module, mock_dummy_server_module, mock_dummy_ui_module)
# If not, define them here or in a conftest.py


# Dummy Service Implementation for testing
class DummyService(AbstractService):
    def __init__(
        self,
        name,
        port,
        template,
        target_path,
        custom_param=None,
    ):
        super().__init__(name=name, template=template, target_path=target_path)
        self.custom_param = custom_param
        self.port = port
        self.service_ports = {}  # Ensure service_ports is initialized

    def setup(self, conn):
        pass

    def check(self, conn):
        return {}


# Dummy Server Implementation for testing
class DummyServer(AbstractServer):
    def __init__(
        self, ip, root, root_pw, port="22", custom_server_param=None, MLOX_IP=None
    ):
        super().__init__(ip=ip, root=root, root_pw=root_pw, port=port)
        self.custom_server_param = custom_server_param
        self.MLOX_IP = MLOX_IP
        self.mlox_user = None  # Mock mlox_user for tests that might need it

    def update(self):
        pass

    def install_packages(self):
        pass

    def add_mlox_user(self):
        pass

    def setup_users(self):
        pass

    def enable_password_authentication(self):
        pass

    def disable_password_authentication(self):
        pass

    def get_server_info(self):
        return {
            "cpu_count": 0,
            "ram_gb": 0,
            "storage_gb": 0,
            "pretty_name": "dummy",
            "host": "dummyhost",
        }

    def git_clone(self, repo_url, path):
        pass

    def git_pull(self, path):
        pass

    def git_remove(self, path):
        pass

    def setup_docker(self):
        pass

    def teardown_docker(self):
        pass

    def get_docker_status(self):
        return {}

    def start_docker_runtime(self):
        pass

    def stop_docker_runtime(self):
        pass

    def setup_kubernetes(self, controller_url=None, controller_token=None):
        pass

    def teardown_kubernetes(self):
        pass

    def get_kubernetes_status(self):
        return {}

    def start_kubernetes_runtime(self):
        pass

    def stop_kubernetes_runtime(self):
        pass


# Dummy UI functions for testing
def dummy_settings_func(
    infra: Infrastructure, bundle: Bundle, service: AbstractService
):
    return {"ui_param_settings": "settings_value", "service_name": service.name}


def dummy_setup_func(infra: Infrastructure, bundle: Bundle):
    return {"ui_param_setup": "setup_value"}


@pytest.fixture
def mock_dummy_service_module(monkeypatch):
    class MockModule:
        DummyService = DummyService

    monkeypatch.setattr(
        importlib,
        "import_module",
        lambda name: MockModule()
        if name == "dummy.services"
        else __import__(name, fromlist=["object"]),
    )


@pytest.fixture
def mock_dummy_server_module(monkeypatch):
    class MockModule:
        DummyServer = DummyServer

    monkeypatch.setattr(
        importlib,
        "import_module",
        lambda name: MockModule()
        if name == "dummy.servers"
        else __import__(name, fromlist=["object"]),
    )


@pytest.fixture
def mock_dummy_ui_module(monkeypatch):
    class MockUiModule:
        dummy_settings_func = dummy_settings_func
        dummy_setup_func = dummy_setup_func

    monkeypatch.setattr(
        importlib,
        "import_module",
        lambda name: MockUiModule()
        if name == "dummy.ui"
        else __import__(name, fromlist=["object"]),
    )


@pytest.fixture
def base_service_config_data():
    return {
        "name": "TestService",
        "version": "1.0",
        "maintainer": "tester",
        "description": "A test service.",
        "description_short": "Test service.",
        "links": {"docs": "http://example.com/docs"},
        "requirements": {"cpu": 1.0, "ram_gb": 2.0},
        "build": {
            "class_name": "dummy.services.DummyService",
            "params": {"custom_param": "build_value"},
        },
        "ports": {"http": 8080},
        "groups": {"backend": {"docker": {}}},
        "ui": {
            "settings": "dummy.ui.dummy_settings_func",
            "setup": "dummy.ui.dummy_setup_func",
        },
    }


@pytest.fixture
def base_server_config_data():
    return {
        "name": "TestServer",
        "versions": ["1.0", 24.04],
        "maintainer": "tester",
        "description": "A test server.",
        "links": {"home": "http://example.com"},
        "build": {
            "class_name": "dummy.servers.DummyServer",
            "params": {"custom_server_param": "build_value"},
        },
    }


class TestServiceConfig:
    def test_service_config_creation(self, base_service_config_data):
        build_config = BuildConfig(**base_service_config_data.pop("build"))
        config = ServiceConfig(**base_service_config_data, build=build_config)
        assert config.name == "TestService"
        assert config.build.class_name == "dummy.services.DummyService"
        assert config.ports["http"] == 8080

    def test_instantiate_ui_success(
        self, base_service_config_data, mock_dummy_ui_module
    ):
        build_config = BuildConfig(**base_service_config_data.pop("build"))
        config = ServiceConfig(**base_service_config_data, build=build_config)

        settings_func = config.instantiate_ui("settings")
        assert callable(settings_func)
        assert settings_func.__name__ == "dummy_settings_func"

        setup_func = config.instantiate_ui("setup")
        assert callable(setup_func)
        assert setup_func.__name__ == "dummy_setup_func"

    def test_instantiate_ui_not_found(self, base_service_config_data, caplog):
        build_config = BuildConfig(**base_service_config_data.pop("build"))
        config = ServiceConfig(**base_service_config_data, build=build_config)
        assert config.instantiate_ui("non_existent_ui") is None
        # No error log expected here, it's normal behavior

    def test_instantiate_ui_import_error(
        self, base_service_config_data, monkeypatch, caplog
    ):
        build_config = BuildConfig(**base_service_config_data.pop("build"))
        config = ServiceConfig(**base_service_config_data, build=build_config)
        config.ui["broken_ui"] = "nonexistent.module.broken_func"

        def mock_import_error(name):
            if name == "nonexistent.module":
                raise ImportError("Mock import error")
            return __import__(name, fromlist=["object"])

        monkeypatch.setattr(importlib, "import_module", mock_import_error)

        assert config.instantiate_ui("broken_ui") is None
        assert "Could not load callable broken_func" in caplog.text

    def test_instantiate_build_success(
        self, base_service_config_data, mock_dummy_service_module
    ):
        build_config = BuildConfig(**base_service_config_data.pop("build"))
        config = ServiceConfig(**base_service_config_data, build=build_config)

        runtime_params = {
            "${MLOX_USER}": "test_user",
            "${MLOX_AUTO_PORT_HTTP}": "9090",
            "${MLOX_STACKS_PATH}": "/stacks",
        }
        config.build.params["target_path"] = "/opt/${MLOX_USER}/app"
        config.build.params["port"] = "${MLOX_AUTO_PORT_HTTP}"
        config.build.params["name"] = "service_name"  # Add a name param
        config.build.params["template"] = "dummy_template"  # Add a template param

        service_instance = config.instantiate_build(runtime_params)
        assert service_instance is not None
        assert isinstance(service_instance, AbstractService)
        assert service_instance.custom_param == "build_value"
        assert (
            service_instance.target_path == "/opt/test_user/app"
        )  # Check substitution
        assert (
            "test_user" in service_instance.target_path
        )  # Check direct param passing if constructor allows
        assert service_instance.port == "9090"

    def test_instantiate_build_not_abstract_service(
        self, base_service_config_data, monkeypatch, caplog
    ):
        class NotAService:
            pass

        class MockBadModule:
            not_a_service = NotAService

        monkeypatch.setattr(
            importlib,
            "import_module",
            lambda name: MockBadModule()
            if name == "bad.module"
            else __import__(name, fromlist=["object"]),
        )

        base_service_config_data["build"]["class_name"] = "bad.module.NotAService"
        build_config = BuildConfig(**base_service_config_data.pop("build"))
        config = ServiceConfig(**base_service_config_data, build=build_config)

        assert config.instantiate_build({}) is None
        # assert "is not a subclass of AbstractService" in caplog.text

    def test_instantiate_build_type_error(
        self, base_service_config_data, mock_dummy_service_module, caplog, monkeypatch
    ):
        # Modify build params to cause a TypeError (e.g., missing required arg if DummyService constructor changes)
        # For current DummyService, let's assume 'name' is required and not provided by default in build.params
        base_service_config_data["build"][
            "params"
        ] = {}  # Remove custom_param, name, template, target_path
        # name, template, target_path are now required by DummyService

        config_data = dict(base_service_config_data)
        build_config = BuildConfig(**config_data.pop("build"))
        config = ServiceConfig(**config_data, build=build_config)

        # The constructor will fail because 'name', 'template', 'target_path' are missing
        # and not all ServiceConfig fields are passed by default to the service constructor.
        # The current instantiate_build passes init_params which are derived from build.params.
        # Let's ensure init_params are correctly formed and passed.
        # The error will be "missing X required positional arguments"

        # To make this test more explicit for TypeError, let's assume DummyService needs 'mandatory_arg'
        # and we don't provide it.
        original_init = DummyService.__init__

        def faulty_init(self, name, template, target_path, mandatory_arg, **kwargs):
            original_init(self, name, template, target_path, **kwargs)
            self.mandatory_arg = mandatory_arg

        monkeypatch.setattr(DummyService, "__init__", faulty_init)

        # Now, instantiate_build will try to call DummyService without 'mandatory_arg'
        # It will pass 'name', 'template', 'target_path' from the ServiceConfig itself.
        # And 'custom_param' from build.params.
        # But 'mandatory_arg' is missing.

        # We need to ensure that the parameters passed to the constructor are only those defined in
        # build.params after substitution.
        # The current ServiceConfig.instantiate_build passes all fields of ServiceConfig as kwargs
        # plus the substituted build.params. This might not be intended.
        # Let's refine the test based on the *actual* behavior of instantiate_build.
        # The actual behavior: init_params = substituted self.build.params.
        # Then service_instance = service_class(**init_params)

        # So, if DummyService requires 'name', 'template', 'target_path' and they are NOT in build.params,
        # it will fail.

        # Let's make DummyService require 'name', 'template', 'target_path' only.
        # And remove them from build.params to cause the error.
        base_service_config_data["build"]["params"] = {
            "custom_param": "val"
        }  # 'name', 'template', 'target_path' are missing

        # Modify DummyService to strictly require these
        def strict_init(self, name, template, target_path, custom_param=None, **kwargs):
            super(DummyService, self).__init__(
                name, template, target_path, **kwargs
            )  # Call parent's init
            self.custom_param = custom_param

        monkeypatch.setattr(DummyService, "__init__", strict_init)

        build_config = BuildConfig(**base_service_config_data.pop("build"))
        config = ServiceConfig(**base_service_config_data, build=build_config)

        # The call will be DummyService(**{"custom_param":"val"}), which misses name, template, target_path
        assert config.instantiate_build({}) is None
        assert (
            "Error calling constructor for dummy.services.DummyService" in caplog.text
        )
        assert (
            "missing 3 required positional arguments: 'name', 'template', and 'target_path'"
            in caplog.text
        )  # or similar based on exact signature

        # Restore original init
        monkeypatch.setattr(DummyService, "__init__", original_init)


class TestServerConfig:
    def test_server_config_creation(self, base_server_config_data):
        build_config = BuildConfig(**base_server_config_data.pop("build"))
        config = ServerConfig(**base_server_config_data, build=build_config)
        assert config.name == "TestServer"
        assert config.build.class_name == "dummy.servers.DummyServer"
        assert "1.0" in config.versions

    def test_instantiate_success(
        self, base_server_config_data, mock_dummy_server_module
    ):
        build_config = BuildConfig(**base_server_config_data.pop("build"))
        config = ServerConfig(**base_server_config_data, build=build_config)

        runtime_params = {
            "${MLOX_IP}": "127.0.0.1",
            "${MLOX_ROOT}": "root",
            "${MLOX_ROOT_PW}": "pw",
        }
        # Add a param to build.params that needs substitution and is part of DummyServer constructor
        config.build.params["ip"] = "${MLOX_IP}"
        config.build.params["root"] = "${MLOX_ROOT}"
        config.build.params["root_pw"] = "${MLOX_ROOT_PW}"

        server_instance = config.instantiate(runtime_params)
        assert isinstance(server_instance, DummyServer)
        assert server_instance.ip == "127.0.0.1"
        assert server_instance.root == "root"
        assert (
            server_instance.custom_server_param == "build_value"
        )  # From original build.params

    def test_instantiate_not_abstract_server(
        self, base_server_config_data, monkeypatch, caplog
    ):
        class NotAServer:
            pass

        class MockBadModule:
            not_a_server = NotAServer()

        monkeypatch.setattr(
            importlib,
            "import_module",
            lambda name: MockBadModule()
            if name == "bad.module"
            else __import__(name, fromlist=["object"]),
        )

        base_server_config_data["build"]["class_name"] = "bad.module.NotAServer"
        build_config = BuildConfig(**base_server_config_data.pop("build"))
        config = ServerConfig(**base_server_config_data, build=build_config)

        assert config.instantiate({}) is None
        # assert "is not a subclass of AbstractServer" in caplog.text


def create_yaml_file(tmp_path, name, content, prefix="mlox"):
    file_path = tmp_path / f"{prefix}.{name}.yaml"
    with open(file_path, "w") as f:
        yaml.dump(content, f)
    return file_path


class TestConfigLoading:
    def test_load_service_configs_success(
        self, tmp_path, base_service_config_data, mock_dummy_service_module
    ):
        create_yaml_file(tmp_path, "test_service", base_service_config_data)
        configs = load_service_configs(str(tmp_path))
        assert len(configs) == 1
        assert isinstance(configs[0], ServiceConfig)
        assert configs[0].name == "TestService"

    def test_load_service_configs_empty_dir(self, tmp_path):
        configs = load_service_configs(str(tmp_path))
        assert len(configs) == 0

    def test_load_service_configs_no_matching_files(self, tmp_path):
        (tmp_path / "other.txt").write_text("data")
        configs = load_service_configs(str(tmp_path))
        assert len(configs) == 0

    def test_load_service_configs_invalid_yaml_format(self, tmp_path, caplog):
        file_path = tmp_path / "mlox.bad_format.yaml"
        file_path.write_text("not a dictionary")
        configs = load_service_configs(str(tmp_path))
        assert len(configs) == 0  # Should skip or handle error gracefully
        assert "Invalid format" in caplog.text

    def test_load_service_configs_yaml_error(self, tmp_path, caplog):
        file_path = tmp_path / "mlox.yaml_error.yaml"
        file_path.write_text(
            "name: Test\nversion: 1.0\nbuild: {class_name: dummy.services.DummyService, params: {key: value"
        )  # Malformed
        configs = load_service_configs(str(tmp_path))
        assert "Error parsing YAML file" in caplog.text

    def test_load_service_configs_missing_required_field(
        self, tmp_path, base_service_config_data, caplog
    ):
        incomplete_data = base_service_config_data.copy()
        del incomplete_data["name"]  # Remove a required field
        create_yaml_file(tmp_path, "incomplete_service", incomplete_data)
        configs = load_service_configs(str(tmp_path))
        # This will likely result in a TypeError when ServiceConfig(**service_data) is called
        assert "Error initializing ServiceConfig" in caplog.text
        assert (
            "missing 1 required positional argument: 'name'" in caplog.text
            or "required keyword-only argument" in caplog.text
        )

    def test_load_all_service_configs(
        self, tmp_path, base_service_config_data, mock_dummy_service_module
    ):
        stack1_dir = tmp_path / "stack1"
        stack1_dir.mkdir()
        create_yaml_file(stack1_dir, "service1", base_service_config_data)

        stack2_dir = tmp_path / "stack2"
        stack2_dir.mkdir()
        service2_data = base_service_config_data.copy()
        service2_data["name"] = "ServiceTwo"
        create_yaml_file(stack2_dir, "service2", service2_data)

        (tmp_path / "other_file.txt").write_text("ignore me")

        all_configs = load_all_service_configs(str(tmp_path))
        assert len(all_configs) == 2
        assert any(c.name == "TestService" for c in all_configs)
        assert any(c.name == "ServiceTwo" for c in all_configs)

    def test_load_server_configs_success(
        self, tmp_path, base_server_config_data, mock_dummy_server_module
    ):
        create_yaml_file(
            tmp_path, "test_server", base_server_config_data, prefix="mlox-server"
        )
        configs = load_server_configs(str(tmp_path))
        assert len(configs) == 1
        assert isinstance(configs[0], ServerConfig)
        assert configs[0].name == "TestServer"

    def test_load_all_server_configs(
        self, tmp_path, base_server_config_data, mock_dummy_server_module
    ):
        stack1_dir = tmp_path / "stack1"
        stack1_dir.mkdir()
        create_yaml_file(
            stack1_dir, "server1", base_server_config_data, prefix="mlox-server"
        )

        all_configs = load_all_server_configs(str(tmp_path))
        assert len(all_configs) == 1
        assert all_configs[0].name == "TestServer"

    def test_load_configs_nonexistent_dir(self, caplog):
        configs = load_service_configs("./nonexistent_dir")
        assert len(configs) == 0
        assert "Configuration directory not found" in caplog.text
        caplog.clear()
        configs = load_all_service_configs("./nonexistent_dir")
        assert len(configs) == 0
        assert "Configuration directory not found" in caplog.text

    def test_service_config_default_factories(self):
        # Test that default factories for ports, groups, ui work
        required_fields = {
            "name": "MinimalService",
            "version": "0.1",
            "maintainer": "min",
            "description": "min desc",
            "description_short": "min short",
            "links": {},
            "requirements": {},
            "build": {"class_name": "dummy.services.DummyService"},
        }
        build_config = BuildConfig(**required_fields.pop("build"))
        config = ServiceConfig(**required_fields, build=build_config)
        assert config.ports == {}
        assert config.groups == {}
        assert config.ui == {}

        # Check all fields are present
        config_fields = {f.name for f in fields(ServiceConfig)}
        expected_fields = {
            "name",
            "version",
            "maintainer",
            "description",
            "description_short",
            "links",
            "requirements",
            "build",
            "ports",
            "groups",
            "ui",
        }
        assert config_fields == expected_fields

    def test_server_config_fields_present(self):
        # Check all fields are present for ServerConfig
        config_fields = {f.name for f in fields(ServerConfig)}
        expected_fields = {
            "name",
            "versions",
            "maintainer",
            "description",
            "links",
            "build",
        }
        assert config_fields == expected_fields
