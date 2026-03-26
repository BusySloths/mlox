# Plugin Guide

> **Source:** [`docs/PLUGIN_CONFIGS.md`](https://github.com/BusySloths/mlox/blob/main/docs/PLUGIN_CONFIGS.md)

MLOX discovers third-party service and server template plugins through Python **entry points**:

- `mlox.service_plugins`
- `mlox.server_plugins`

Each entry point must return a `ServiceConfig` instance.

---

## Contents

1. [Minimal Plugin Package Example](#minimal-plugin-package-example)
2. [How Plugin Discovery Works](#how-plugin-discovery-works)
3. [YAML Configuration Fields](#yaml-configuration-fields)

---

## Minimal Plugin Package Example

### `pyproject.toml`

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

### `my_mlox_plugin/plugin.py`

```python
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

### Install the Plugin

```bash
pip install my-mlox-plugin
```

Install the plugin package in the same environment as MLOX and it will be automatically discoverable.

---

## How Plugin Discovery Works

Plugin loading is wired in [`mlox/config.py`](https://github.com/BusySloths/mlox/blob/main/mlox/config.py) via **entry-point discovery**.

Once installed, external plugins are automatically included in:

- `load_all_service_configs()`
- `load_all_server_configs()`

Most callers do not need any code changes to benefit from external plugins.

---

## YAML Configuration Fields

When authoring a plugin service config, the key YAML fields are:

| Field | Purpose |
|-------|---------|
| `build.class_name` | Maps the config to its Python implementation class |
| `ports` | Declares intended port bindings (remappable at setup time) |
| `groups` | Descriptive grouping; some values map to functional classes (e.g., `git`) |
| `ui` | Controls how the service appears in the interfaces |
| `requirements` | Declares service dependencies _(not yet fully enforced at runtime)_ |

---

## See Also

- [Home](Home) — Project overview
- [Architecture](Architecture) — Codebase walkthrough
- [`docs/PLUGIN_CONFIGS.md`](https://github.com/BusySloths/mlox/blob/main/docs/PLUGIN_CONFIGS.md) — Source document
- [API Docs](https://busysloths.github.io/mlox/mlox.html) — Full API reference
