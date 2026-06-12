# UI Registry

This package connects configuration IDs to frontend-specific handlers.

## Structure

- `registry.py`: registration, lazy bootstrap, and handler lookup.

Handlers are keyed by frontend, function name, and service or server config ID.

## Workflow

1. Streamlit or TUI modules register built-in handlers.
2. A loaded config requests a handler such as `setup` or `settings`.
3. The active frontend invokes it with infrastructure and runtime objects.

## System Role

The registry keeps frontend imports out of domain and service configuration
models. Do not put Streamlit or Textual callables in YAML files.

