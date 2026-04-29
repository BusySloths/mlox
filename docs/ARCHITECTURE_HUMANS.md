# MLOX Core Architecture (Human Contributor Guide)

This document gives a practical, contributor-first map of the MLOX codebase.

## 1) Fast orientation

MLOX is a Python project that manages MLOps infrastructure through three user interfaces:

- **CLI** (`mlox/cli/`)
- **TUI** (`mlox/tui/`)
- **Web app (Streamlit)** (`mlox/view/`)

The current CLI architecture routes through a thin application layer before it reaches the core runtime objects:

- **`mlox/application/facade.py`**: stateless session loader/dispatcher
- **`mlox/application/use_cases/`**: session-based application actions grouped by domain
- **`MloxSession`** (`mlox/session.py`): project/session state and persistence
- **`Infrastructure`** (`mlox/infra.py`): servers, bundles, services

```text
CLI (`mlox/cli/app.py` + `mlox/cli/commands/*`)
    └─► `mlox/application/facade.py`
          └─► `mlox/application/use_cases/*`
                └─► `MloxSession`
                      └─► `Infrastructure`

YAML configs are loaded through `mlox/config.py` into that flow.
```

## 2) Setup, tests, and repo surroundings

### Task runner and setup

- The project uses **Go Task** (`task`) as its task runner.
- Main task configuration is in **`taskfile.dist.yml`**.
- This file includes setup and operational tasks such as:
  - environment bootstrap (`first:steps`, `dev:env:create`)
  - VM setup (Multipass install/start/cleanup)
  - running tests (unit + integration)
  - running Docker-based local stack (`docker:up`, `docker:down`)

### Tests

- **Unit tests** live in `tests/unit/` and are expected to run out-of-the-box once the environment is correctly prepared.
- **Integration tests** live in `tests/integration/` and require **Multipass VMs**; they are slower and more expensive to run.

### Other important top-level directories

- `examples/`: user-oriented usage snippets.
- `docs/`: project documentation.
- `scripts/`: currently a hacky/experimental area; not a stable architecture reference.
- `website/`: Astro-based landing page site.

### Documentation and packaging pipeline

- **pdoc** is used to generate API docs for GitHub Pages (see workflows).
- The package is configured for publication to **PyPI** (`pyproject.toml`, deploy workflow).

## 3) Main library architecture (`mlox/`)

The `mlox/` package contains:

- `services/`: deployable MLOps services
- `servers/`: backend/server abstractions and implementations
- `application/`: facade plus session-based use-cases
- `tui/`: Textual terminal UI
- `view/`: Streamlit web app
- `cli/`: Typer CLI package (`app.py` + `commands/*`)
- `assets/`: includes some outdated scripts/assets (not always canonical)

### Configuration-driven building

Services and servers are built from YAML configurations loaded through `mlox/config.py`:

- YAML metadata defines service/server identity and build class
- `build.class_name` maps config to Python implementation class
- `ports`, `groups`, `ui`, `requirements` etc. are read from YAML
- Plugin loading is also wired in `config.py` (entry-point discovery)

## 4) Core runtime data model

### `MloxSession` is the central entry point

`MloxSession` (`mlox/session.py`) is the main runtime object that:

- loads/creates a project
- wires a secret manager
- loads/saves project infrastructure

### `Infrastructure` holds one project’s active topology

`Infrastructure` (`mlox/infra.py`) contains the project’s server bundles and services for a session/project.

### Persistent storage model

- Runtime structures are dataclass-based and serialized to JSON-compatible dicts.
- Project and infrastructure data are stored through a **secret manager** abstraction.
- In practice, a session always has a secret manager configured (fallback to in-memory if needed).

## 5) Secret manager model

MLOX supports multiple secret-manager implementations:

- MLOX-native/lightweight:
  - `InMemorySecretManager`
  - `TinySecretManager`
- External integrations:
  - OpenBao (service + client under `mlox/services/openbao/`)
  - GCP Secret Manager (`mlox/services/gcp/secret_manager.py`)

The `MloxProject` metadata stores which secret manager class is used and how to reconnect to it.

## 6) Service lifecycle and execution model

### Shared control flow

The CLI now goes through `mlox/cli/commands/*` -> `mlox/application/facade.py` -> `mlox/application/use_cases/*` -> `MloxSession` -> `Infrastructure`.

TUI and Web UI should preserve the same session/infrastructure behavior even where they do not yet share the exact same presentation-layer wiring.

### Executors do system calls

- Services/servers should route low-level command execution through task executors (`mlox/executors.py` + server executors).
- Operational system calls should not be scattered arbitrarily inside service logic.

### Port assignment behavior

- YAML config declares intended ports.
- During infrastructure setup, ports can be remapped to avoid collisions.

## 7) Design notes / current limitations

- `mlox/scheduler.py` exists but is effectively legacy/obsolete in day-to-day architecture.
- `mlox/application/facade.py` is now a thin stateless facade that loads/caches session context and dispatches to `application/use_cases/*`.
- `mlox/application/infrastructure_ops.py` holds orchestration helpers used by the session-based use-cases for setup/teardown-style side effects.
- YAML `requirements` are present in config schema but currently not fully enforced in runtime.
- YAML `groups` are partly descriptive today; some map to functional behavior/classes (e.g., git), but this is not yet fully consistent.

## 8) Backend abstraction

MLOX is backend-agnostic at architecture level. Current backends include:

- native
- docker
- kubernetes

The design aims to make additional backends relatively straightforward to add (e.g., new Kubernetes flavors or custom platforms).

## 9) Services and servers: authoring conventions

- Each service has a dedicated MLOX YAML config.
- Servers also have MLOX YAML configs.
- Services usually include backend-specific implementation classes and required deployment files (e.g., Docker Compose templates).
- Some services expose helper clients (`client.py` or similar) so users can consume service functionality from Python code via the package.
- Services can depend on other services:
  - dependency UUIDs are stored on service objects
  - dependent services are resolved via helper methods (e.g., `get_dependend_service` pattern)
- Each service should expose `get_secret()` returning access-relevant credentials/details (user/password/endpoint/etc.).
