# Textual TUI

This package implements the terminal dashboard using Textual.

## Structure

- `app.py`: application lifecycle and project login.
- `screens/login.py`: open and create project flow.
- `screens/dashboard/`: infrastructure tree, details, actions, and logs.
- `services/`: TUI-specific service panels.

## Workflow

Login stores one `ProjectWorkspace` on the app. Dashboard widgets render its
infrastructure and invoke workspace operations. Reloading refreshes both the
workspace and visible tree state.

## System Role

The TUI is a stateful frontend adapter. Keep deployment logic and persistence
outside widgets and screens.

