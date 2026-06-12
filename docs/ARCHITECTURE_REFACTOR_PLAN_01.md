# Architecture Refactor Status

This document is a compact status note for the architecture simplification work started in 2026.

## Completed

- The old large CLI module was split into `mlox/cli/app.py`, `mlox/cli/commands/*`, rendering helpers, and context helpers.
- The application layer has project-based use cases under `mlox/application/use_cases/`.
- `ProjectWorkspace` controls commit/reload behavior as the only public project runtime.
- Internal `WorkspaceState` contains metadata and infrastructure.
- `Infrastructure` contains topology queries, serialization, and runtime hydration only.
- Frontend-specific setup handlers are outside YAML and are resolved through `mlox/ui/registry.py`.

## Current Architecture

Current runtime flow:

```text
CLI / TUI / Streamlit
        |
        v
ProjectWorkspace
        |
        v
internal WorkspaceState + SqlCipherRepository
        |
        v
Infrastructure -> Bundle(server + services)
```

Server, service, and model orchestration lives in focused use-case modules.
Use cases accept `WorkspaceState`; persistence remains controlled by
`ProjectWorkspace` through the internal repository.

## Still Open

1. Add clearer port, naming, and dependency policies.
2. Keep service capability metadata moving toward a real placement model.
3. Continue moving specialized UI settings mutations behind application methods.
4. Add PostgreSQL repository support behind the existing data-source boundary.

## Practical Direction

Avoid a large package rename. The current paths are already usable and known:

- `mlox/cli/`
- `mlox/tui/`
- `mlox/view/`
- `mlox/application/`
- `mlox/infra.py`
- `mlox/project/workspace.py`
- `mlox/config.py`

Prefer incremental moves:

- keep UI code thin
- grow use-cases for shared workflows
- keep executor boundaries intact
- keep persistence out of use cases and topology objects

## Done Criteria For The Remaining Refactor

- Service lookup has one authoritative path.
- Standard UI lifecycle commands do not mutate infrastructure directly.
- Domain/topology objects are testable independently from persistence.
- Config loading remains backward compatible for existing YAML and plugins.
- Adding a new UI path mostly means wiring to existing use-cases.
