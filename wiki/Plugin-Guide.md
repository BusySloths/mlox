# Plugin Guide

> **Source:** [`docs/PLUGIN_CONFIGS.md`](https://github.com/BusySloths/mlox/blob/main/docs/PLUGIN_CONFIGS.md)  
> How to create and register external service and server plugins for MLOX.

---

## Contents

1. [Overview](#overview)
2. [Entry Points](#entry-points)
3. [Minimal Plugin Example](#minimal-plugin-example)
4. [How Plugin Loading Works](#how-plugin-loading-works)

---

## Overview

MLOX discovers third-party template plugins through **Python entry points**. This lets you ship an external plugin package that adds new services or server types without modifying the MLOX core.

---

## Entry Points

| Entry Point | Purpose |
|-------------|---------|
| `mlox.service_plugins` | Register new deployable services |
| `mlox.server_plugins` | Register new server backends |

Each entry point must return a `ServiceConfig` instance.

---

## Minimal Plugin Example

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

### Install

```bash
pip install my-mlox-plugin
```

Install the plugin into the same Python environment as MLOX. It will be automatically discoverable through template listing commands.

---

## How Plugin Loading Works

Plugin discovery is handled by [`mlox/config.py`](https://github.com/BusySloths/mlox/blob/main/mlox/config.py) via Python's entry-point mechanism.

Once installed, plugins are automatically included in:

- `load_all_service_configs()` — returns all built-in + plugin service configs
- `load_all_server_configs()` — returns all built-in + plugin server configs

No code changes are required in the MLOX core to benefit from an installed plugin.

---

## See Also

- [Home](Home) — Project overview
- [Services Catalog](Services-Catalog) — All built-in MLOX services
- [Architecture](Architecture) — Config system and plugin entry-point details
- [`docs/PLUGIN_CONFIGS.md`](https://github.com/BusySloths/mlox/blob/main/docs/PLUGIN_CONFIGS.md) — Source document
