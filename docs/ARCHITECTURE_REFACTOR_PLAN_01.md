# Architecture Refactor Status

This document is a compact status note for the architecture simplification work started in 2026.

## Completed

- The old large CLI module was split into `mlox/cli/app.py`, `mlox/cli/commands/*`, rendering helpers, and context helpers.
- The application layer now has focused session-based use-cases under `mlox/application/use_cases/`.
- `mlox/application/facade.py` is now a thin adapter for callers that need session loading/caching.
- Frontend-specific setup handlers are outside YAML and are resolved through `mlox/ui/registry.py`.

## Current Architecture

Current runtime flow:

```text
CLI / TUI / Streamlit
        |
        v
mlox/application/use_cases/*
        |
        v
MloxSession
        |
        v
Infrastructure
        |
        v
Bundle(server + services)
```

`Infrastructure` still contains compatibility methods around lifecycle behavior. Side-effectful orchestration is increasingly concentrated in `mlox/application/infrastructure_ops.py`, but this separation is not complete.

## Still Open

1. Make `Infrastructure` the single source of truth for service lookup.
2. Move more setup/teardown orchestration out of topology entities and into application-layer handlers.
3. Add clearer port/naming/dependency policies.
4. Keep service capability metadata moving toward a real placement model.
5. Add boundary tests around config loading, session reload, service dependency lookup, and CLI/use-case behavior.

## Practical Direction

Avoid a large package rename. The current paths are already usable and known:

- `mlox/cli/`
- `mlox/tui/`
- `mlox/view/`
- `mlox/application/`
- `mlox/infra.py`
- `mlox/session.py`
- `mlox/config.py`

Prefer incremental moves:

- keep UI code thin
- grow use-cases for shared workflows
- keep executor boundaries intact
- remove compatibility wrappers only after tests cover the replacement path

## Done Criteria For The Remaining Refactor

- Service lookup has one authoritative path.
- UI commands do not mutate infrastructure directly.
- Domain/topology objects are testable without network or subprocess calls.
- Config loading remains backward compatible for existing YAML and plugins.
- Adding a new UI path mostly means wiring to existing use-cases.
