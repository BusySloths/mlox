# Streamlit UI

This package implements the browser-based MLOX interface.

## Structure

- Page modules such as `infrastructure.py`, `services_page.py`, and
  `secret_manager.py`.
- `services/`: service-specific setup and settings panels.
- `servers/`: server-specific setup panels.
- `utils.py`: shared Streamlit helpers.

## Workflow

The login page creates or opens a `ProjectWorkspace` in Streamlit session state.
Pages read from that workspace and call its public operations. Specialized
panels are resolved through `mlox.ui`.

## System Role

Keep pages focused on layout, input, and feedback. Shared behavior belongs in
the workspace or application use cases, not in Streamlit callbacks.

