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

## Capability contracts

Implementations can import capability enums and abstract contracts from
`mlox.contracts.services` and `mlox.contracts.servers`. The existing
`mlox.service` and `mlox.server` imports remain supported and reference the same
objects. Advertise supported capabilities in both the implementation class and
config. Config loading checks known declarations against implementation classes
and logs warnings for mismatches; capability declarations are not a complete
placement policy.

For example, an S3-compatible storage service implements
`AbstractS3ObjectStorageService` and advertises both `object_storage` and
`s3_object_storage`. Its `get_storage(infra)` returns an object-storage client
with `list_keys`, `read_bytes`, and `write_bytes`; connection details and
credentials are exported through `get_secrets()`. The S3 capability marks API
compatibility; it does not promise every optional S3 operation.

```yaml
capabilities:
  service:
    - object_storage
    - s3_object_storage
  backend:
    - docker
```

## UI Handlers

Plugin entry points currently cover config discovery only. Frontend UI setup handlers (TUI, plus the deprecated Streamlit UI until its extraction) are not declared in YAML and are not yet part of the documented external plugin API.

The built-in pattern is:

1. YAML or plugin config declares the deployable service/server.
2. Frontend modules implement custom setup/settings handlers.
3. `mlox/ui/registry.py` registers handlers by `config_id`, frontend, and function name.
