# Core Architecture Simplification Plan

## Why now

The current codebase already states a shared flow through `MloxSession` and `Infrastructure`, but several responsibilities are still mixed:

- `mlox/cli.py` is very large and contains both command wiring and presentation/formatting concerns.
- `mlox/operations.py` centralizes use-cases but is currently a broad, flat module.
- `mlox/infra.py` mixes topology state with orchestration/runtime tasks.
- A singleton `service_registry` exists in parallel to `Infrastructure`, creating two sources of truth for services.

This plan proposes a clean architecture that keeps the strengths of the current model while reducing coupling.

## Target architecture (layered + ports/adapters)

### 1) Presentation Layer

**Goal:** keep user interfaces thin.

- `interfaces/cli/` (Typer only: args/options -> use-case input models)
- `interfaces/tui/`
- `interfaces/web/`

No business logic, no direct infrastructure mutation, no registry lookup.

### 2) Application Layer (Use-cases)

**Goal:** explicit use-cases as stable API for all UIs.

- `application/use_cases/project.py`
- `application/use_cases/servers.py`
- `application/use_cases/services.py`
- `application/use_cases/models.py`

Use-cases return standardized DTOs/results (keep `OperationResult` style but move to `application/result.py`).

### 3) Domain Layer

**Goal:** pure domain model + invariants.

- `domain/infrastructure.py` (entities: `Infrastructure`, `Bundle`, `ServiceRef`)
- `domain/policies/` (port allocation policy, naming policy, dependency policy)
- `domain/events.py` (service added/removed events)

This layer must not depend on Typer, subprocess, YAML loaders, or singleton registries.

### 4) Infrastructure/Adapters Layer

**Goal:** IO and framework integration only.

- config loading adapters (YAML/plugin loading)
- persistence adapters (secret manager/session storage)
- runtime adapters (server executors, docker/k8s/native drivers)
- observability/log adapters

## Key structural decisions

## A) Split `cli.py` into command modules

Suggested structure:

- `mlox/cli/app.py` (root app wiring)
- `mlox/cli/commands/project.py`
- `mlox/cli/commands/server.py`
- `mlox/cli/commands/service.py`
- `mlox/cli/commands/model.py`
- `mlox/cli/rendering/table.py` (formatting-only helpers)
- `mlox/cli/context.py` (credential/session option resolution)

Result: CLI remains easy to navigate and test with command-focused unit tests.

## B) Replace monolithic operations module with focused use-case modules

Instead of one long `operations.py`, split by domain capabilities.

Example pattern:

- `application/use_cases/servers.py`
- `application/use_cases/services.py`
- `application/use_cases/models.py`

Each module should expose small, explicit functions, for example:

- `list_servers(load_session, project, password)`
- `add_server(load_session, load_server_config, ...)`
- `setup_service(load_session, project, password, name=...)`

Prefer passing a small number of concrete helper functions over introducing
ports/protocols unless the abstraction is already paying for itself.

This keeps CLI/TUI/Web consumers interchangeable while staying easy to read
and test.

## C) Make `Infrastructure` the single source of truth (remove parallel registry)

Current singleton `service_registry` duplicates service indexing.

Refactor plan:

1. Introduce an internal index on `Infrastructure`:
   - `services_by_uuid: dict[str, AbstractService]`
   - optional `services_by_name: dict[str, str]`
2. Keep index updates inside `add_service`, `teardown_service`, `remove_bundle`.
3. Expose lookup methods on `Infrastructure`:
   - `get_service_by_uuid(...)`
   - `get_service_by_name(...)`
4. Remove direct singleton usage from service dependency resolution.
5. Provide a temporary compatibility adapter that proxies old calls to new lookups during migration.

## D) Move orchestration out of domain entities

`Infrastructure.setup_service()` / teardown behavior should move to application service handlers.

- Domain entities mutate state and validate invariants.
- Application use-cases orchestrate side effects (connection creation, setup/spin-up calls, persistence).

This avoids anemic use-cases and makes runtime effects explicit.

## E) Introduce explicit ports (interfaces)

Define small contracts to decouple use-cases from implementation details:

- `ProjectSessionPort` (load/save project state)
- `ServiceCatalogPort` (list/load service templates)
- `ServerCatalogPort`
- `ServiceRuntimePort` (setup/spin-up/spin-down)
- `ModelRegistryPort`

Then implement adapters over existing modules (`session.py`, `config.py`, server executors).

## Migration roadmap (safe, incremental)

### Phase 0: Baseline and guardrails

- Add architecture tests around current critical workflows (create project, add server, add/setup service).
- Add snapshot/contract tests for CLI output where needed.

### Phase 1: CLI decomposition (no behavior change)

- Move command groups and rendering helpers into new files.
- Keep delegating to existing operations functions.

### Phase 2: Operations decomposition

- Create `application/use_cases/*` modules.
- Migrate one command family at a time (servers first, then services, then models).
- Keep `operations.py` as deprecated facade calling new use-cases.

### Phase 3: Registry unification

- Add service indexes to `Infrastructure`.
- Redirect dependency lookups to `Infrastructure` methods.
- Deprecate and remove singleton registry module.

### Phase 4: Domain/application separation

- Move runtime side effects from domain entity methods to use-cases.
- Keep entities focused on state transitions and invariants.

### Phase 5: Clean-up and hardening

- Delete deprecated facades.
- Ensure docs match final architecture.
- Add lint rules/import boundaries if desired.

## Suggested module map after refactor

- `mlox/domain/...`
- `mlox/application/...`
- `mlox/adapters/...`
- `mlox/interfaces/cli/...`
- `mlox/interfaces/tui/...`
- `mlox/interfaces/web/...`

(You can keep existing package paths and migrate progressively to avoid a big-bang rewrite.)

## Practical engineering heuristics

- Prefer **strangler pattern** over full rewrite.
- Keep old and new entrypoints temporarily, behind small facades.
- Make every migration step reversible.
- Track architecture debt with ADRs (one ADR per major decision).
- Set a hard cap for module size (e.g., 300 lines) for new modules.

## Definition of done for this initiative

- No single file owning both CLI rendering + business logic + orchestration.
- One source of truth for service lookup/lifecycle state.
- Use-cases shared by CLI/TUI/Web without UI-specific branching.
- Domain logic testable without network/subprocess.
- Adding a new UI command path requires no edits to core domain objects.
