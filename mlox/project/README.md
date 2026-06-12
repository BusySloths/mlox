# Project Runtime

This package owns encrypted project state and the public project API.

## Structure

- `workspace.py`: public `ProjectWorkspace` lifecycle and mutation boundary.
- `state.py`: internal metadata and infrastructure state.
- `repository.py`: SQLCipher schema, loading, and atomic persistence.
- `secrets.py`: embedded and unavailable secret-manager adapters.

## Workflow

1. Create or open a `ProjectWorkspace`.
2. Read metadata, infrastructure, and the active secret manager from it.
3. Use workspace operations for automatic commit and rollback behavior.
4. For direct SDK mutations, call `workspace.commit()` explicitly.

## System Role

CLI, TUI, and Streamlit all operate on this API. Persistence details stay here;
use cases and frontends must not access SQLCipher directly.

