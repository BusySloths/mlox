# Config Plugins

MLOX can discover third-party service and server configs from Python entry points.

Entry-point groups:

- `mlox.service_plugins`
- `mlox.server_plugins`

Each entry point must return a `mlox.config.ServiceConfig` instance. The config should include the same core fields as built-in YAML configs, especially `id`, `name`, `version`, `maintainer`, `description_short`, `description`, `links`, and `build.class_name`.

## Minimal Package

```toml
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
from mlox.config import BuildConfig, ServiceConfig


def service_plugin() -> ServiceConfig:
    config = ServiceConfig(
        id="my-plugin-service",
        name="My Plugin Service",
        version="1.0.0",
        maintainer="Plugin Maintainer",
        description_short="Example external service config.",
        description="Example external service config for MLOX.",
        links={"project": "https://example.com"},
        build=BuildConfig(class_name="my_mlox_plugin.service.MyService"),
    )
    config.path = "external/mlox.my-plugin-service.yaml"
    return config


def server_plugin() -> ServiceConfig:
    config = ServiceConfig(
        id="my-plugin-server",
        name="My Plugin Server",
        version="1.0.0",
        maintainer="Plugin Maintainer",
        description_short="Example external server config.",
        description="Example external server config for MLOX.",
        links={"project": "https://example.com"},
        build=BuildConfig(class_name="my_mlox_plugin.server.MyServer"),
    )
    config.path = "external/mlox-server.my-plugin-server.yaml"
    return config
```

Install the plugin package into the same environment as MLOX:

```bash
pip install my-mlox-plugin
```

After installation, the config is included by normal loading paths such as:

- `load_all_service_configs()`
- `load_all_server_configs()`

## UI Handlers

Plugin entry points currently cover config discovery only. Streamlit/TUI setup handlers are not declared in YAML and are not yet part of the documented external plugin API.

The built-in pattern is:

1. YAML or plugin config declares the deployable service/server.
2. Frontend modules implement custom setup/settings handlers.
3. `mlox/ui/registry.py` registers handlers by `config_id`, frontend, and function name.
