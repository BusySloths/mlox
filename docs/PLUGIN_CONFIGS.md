# External config plugins (minimal example)

MLOX discovers third-party template plugins through Python entry points:

- `mlox.service_plugins`
- `mlox.server_plugins`

Each entry point must return a `ServiceConfig` instance.

These entry points currently cover deployable service/server configs only. Frontend-specific UI handlers are intentionally kept outside YAML and are registered separately through `mlox/ui/registry.py`.

## Minimal package example

```toml
# pyproject.toml
[project]
name = "my-mlox-plugin"
version = "0.1.0"
dependencies = ["busysloths-mlox"]

[project.entry-points."mlox.service_plugins"]
my-service = "my_mlox_plugin.plugin:service_plugin"

[project.entry-points."mlox.server_plugins"]
my-server = "my_mlox_plugin.plugin:server_plugin"
```

```python
# my_mlox_plugin/plugin.py
from mlox.config import BuildConfig, ServiceConfig


def _build_config(config_id: str, path: str, class_name: str) -> ServiceConfig:
    cfg = ServiceConfig(
        id=config_id,
        name=config_id,
        version="1.0",
        maintainer="plugin-author",
        description="External plugin template",
        description_short="External template",
        links={"project": "https://example.com"},
        build=BuildConfig(class_name=class_name),
    )
    cfg.path = path
    return cfg


def service_plugin() -> ServiceConfig:
    return _build_config(
        config_id="my-plugin-service",
        path="external/mlox.my-plugin-service.yaml",
        class_name="my_mlox_plugin.service.MyService",
    )


def server_plugin() -> ServiceConfig:
    return _build_config(
        config_id="my-plugin-server",
        path="external/mlox-server.my-plugin-server.yaml",
        class_name="my_mlox_plugin.server.MyServer",
    )
```

Install the plugin package in the same environment as MLOX (`pip install my-mlox-plugin`) and it will be discoverable through template listing commands.

With this integration, existing template-loading paths automatically include entry-point plugins, e.g.:
- `load_all_service_configs()`
- `load_all_server_configs()`

So most callers do not need any code changes to benefit from external plugins.

## UI registration note

Custom setup/settings panels for Streamlit or TUI are not declared in the YAML config and are not currently part of the plugin entry-point API documented here.

The active pattern in the core codebase is:

- YAML defines the deployable service/server config
- frontend modules implement custom UI handlers
- `mlox/ui/registry.py` registers handlers by `config_id`, `frontend`, and `function_name`

That registry shape is the intended future hook for plugin-contributed UI handlers, but today this guide only documents config plugins.
