from dataclasses import asdict
from importlib import metadata as importlib_metadata

from mlox.config import (
    BuildConfig,
    ServiceConfig,
    discover_server_plugins,
    discover_service_plugins,
    load_all_server_configs,
    load_all_service_configs,
)


class _DummyEntryPoint:
    def __init__(self, provider):
        self._provider = provider

    def load(self):
        return self._provider


class _DummyEntryPoints:
    def __init__(self, providers_by_group):
        self._providers_by_group = providers_by_group

    def select(self, *, group: str):
        providers = self._providers_by_group.get(group, [])
        return [_DummyEntryPoint(provider) for provider in providers]


def _make_plugin_config(config_id: str, path: str) -> ServiceConfig:
    cfg = ServiceConfig(
        id=config_id,
        name="External",
        version="1.0",
        maintainer="plugin",
        description="External plugin config",
        description_short="External",
        links={"project": "https://example.com"},
        build=BuildConfig(class_name="mlox.services.redis.docker.RedisDockerService"),
    )
    cfg.path = path
    return cfg


def test_discover_service_plugins_from_builtin_configs():
    plugins = discover_service_plugins()

    assert plugins
    assert any(plugin["plugin_id"] == "postgres-16-bullseye-docker" for plugin in plugins)
    postgres = next(
        plugin
        for plugin in plugins
        if plugin["plugin_id"] == "postgres-16-bullseye-docker"
    )
    assert postgres["config"].path == "postgres/mlox.postgres.16.yaml"


def test_discover_server_plugins_from_builtin_configs():
    plugins = discover_server_plugins()

    assert plugins
    assert any(plugin["plugin_id"] == "ubuntu-native-24.04-server" for plugin in plugins)


def test_discover_service_plugins_supports_entry_point_service_config(monkeypatch):
    ext_cfg = _make_plugin_config("ext-service", "external/mlox.external.yaml")

    monkeypatch.setattr(
        importlib_metadata,
        "entry_points",
        lambda: _DummyEntryPoints({"mlox.service_plugins": [lambda: ext_cfg]}),
    )

    plugins = discover_service_plugins()

    extension = next(plugin for plugin in plugins if plugin["plugin_id"] == "ext-service")
    assert extension["config"].path == "external/mlox.external.yaml"


def test_discover_server_plugins_supports_entry_point_service_config(monkeypatch):
    ext_cfg = _make_plugin_config(
        "ext-server", "external/mlox-server.external.yaml"
    )

    monkeypatch.setattr(
        importlib_metadata,
        "entry_points",
        lambda: _DummyEntryPoints({"mlox.server_plugins": [lambda: ext_cfg]}),
    )

    plugins = discover_server_plugins()

    extension = next(plugin for plugin in plugins if plugin["plugin_id"] == "ext-server")
    assert asdict(extension["config"]) == asdict(ext_cfg)


def test_load_all_service_configs_includes_entrypoint_plugins(monkeypatch):
    ext_cfg = _make_plugin_config("ext-service-load", "external/mlox.ext-load.yaml")

    monkeypatch.setattr(
        importlib_metadata,
        "entry_points",
        lambda: _DummyEntryPoints({"mlox.service_plugins": [lambda: ext_cfg]}),
    )

    configs = load_all_service_configs()
    assert any(cfg.id == "ext-service-load" for cfg in configs)


def test_load_all_server_configs_includes_entrypoint_plugins(monkeypatch):
    ext_cfg = _make_plugin_config("ext-server-load", "external/mlox-server.ext-load.yaml")

    monkeypatch.setattr(
        importlib_metadata,
        "entry_points",
        lambda: _DummyEntryPoints({"mlox.server_plugins": [lambda: ext_cfg]}),
    )

    configs = load_all_server_configs()
    assert any(cfg.id == "ext-server-load" for cfg in configs)
