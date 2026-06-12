# Application Layer

This package contains reusable MLOX operations independent of any frontend.

## Structure

- `result.py`: common `OperationResult` response type.
- `use_cases/project.py`: project-level operations.
- `use_cases/servers.py`: server lifecycle and queries.
- `use_cases/services.py`: service lifecycle and queries.
- `use_cases/models.py`: model orchestration.

## Workflow

`ProjectWorkspace` calls a use case with internal workspace state, commits a
successful mutation, and reloads state after failure.

## System Role

Use cases coordinate domain objects but do not own persistence, credentials, or
UI rendering. Add shared behavior here instead of duplicating it across
frontends.

