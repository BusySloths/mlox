# MLOX Core Architecture (Human Contributor Guide)

This document gives a practical, contributor-first map of the MLOX codebase.

## 1) Fast orientation

MLOX is a Python project that manages MLOps infrastructure through three user interfaces:

- **CLI** (`mlox/cli/`)
- **TUI** (`mlox/tui/`)
- **Web app (Streamlit)** (`mlox/view/`)

The shared architecture is centered on a session container and session-based use-cases:

- **`mlox/application/use_cases/`**: session-based application actions that should be shared by CLI, TUI, Streamlit, and future UIs
- **`MloxSession`** (`mlox/session.py`): project/session container holding metadata, secret manager, and infrastructure
- **`Infrastructure`** (`mlox/infra.py`): project topology made of bundles, compute, and services
- **`mlox/application/facade.py`**: current stateless adapter used mainly by the CLI and callers that need session loading/caching

```text
CLI     TUI     Streamlit Web UI     Other UIs
  \      |             |                /
   \     |             |               /
    +----+-------------+--------------+
                    |
                    v
      `mlox/application/use_cases/*`
         shared session-based logic
                    |
                    v
              `MloxSession`
   project + encrypted secret manager + infrastructure
             /                               \
            v                                 v
 secret-manager backend                `Infrastructure`
 (InMemory/TinySM/OpenBao/GCP)      topology for one project
                                            |
                                            v
                           `Bundle` = compute/server + services[*]
                              |                            |
                              v                            v
                server capabilities               service capabilities
             (`git`, `docker`, ...)           (emerging: `registry`, `db`, `model`, ...)
                              \                            /
                               \                          /
                                +------------------------+
                                             |
                                             v
                   execution via `mlox/executors.py` + `mlox/execution/*`
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
- always gives the runtime one place to find project metadata, secrets, and topology

### `MloxSession` contains an encrypted key-value secret manager

The session always works with a secret manager instance:

- local/default flows use an encrypted key-value style manager (`InMemorySecretManager` fallback, `TinySecretManager` for lightweight persistence)
- production-facing integrations can swap that backend out (`OpenBao`, `GCP Secret Manager`)
- project metadata remembers which secret manager class to reconnect to

In practice, `MloxSession` is the persistence boundary around `Infrastructure`.

### `Infrastructure` holds one project’s active topology

`Infrastructure` (`mlox/infra.py`) contains the project’s server bundles and services for a session/project.

### `Bundle` groups one compute/server with its services

`Bundle` is the operational unit inside `Infrastructure`:

- one bundle contains one compute/server object
- that compute advertises capabilities such as `git`, `docker`, `kubernetes`, `firewall`, or local/native runtime support
- the same bundle also contains the services deployed onto that compute

This makes `Infrastructure` the topology root for "what runs where".

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

The intended control flow is:

- UI layer (`cli`, `tui`, `view`, future UIs)
- shared application layer (`mlox/application/use_cases/*`)
- session container (`MloxSession`)
- topology root (`Infrastructure`)

The CLI currently reaches that shared layer through `mlox/application/facade.py`. TUI and Streamlit should converge on the same use-cases so behavior stays aligned across interfaces.

`Infrastructure` is primarily the topology model, but it still exposes compatibility wrappers that delegate some lifecycle work into `mlox/application/infrastructure_ops.py`.

### Executors do system calls

- Anything that executes on a compute/server should route through the execution layer.
- In practice that means task executors (`mlox/executors.py`) plus the helper modules in `mlox/execution/`.
- Services receive their executor from the compute/server they are attached to.
- Operational system calls should not be scattered arbitrarily inside service logic.

### Port assignment behavior

- YAML config declares intended ports.
- During infrastructure setup, ports can be remapped to avoid collisions.

## 7) Design notes / current limitations

- `mlox/scheduler.py` exists but is effectively legacy/obsolete in day-to-day architecture.
- `mlox/application/use_cases/*` is the important session-based application layer. Keep growing behavior there instead of reintroducing broad ad-hoc operations modules.
- `mlox/application/facade.py` is a thin stateless adapter that loads/caches session context and dispatches to `application/use_cases/*`.
- `mlox/application/infrastructure_ops.py` holds orchestration helpers used by the session-based use-cases for setup/teardown-style side effects.
- YAML `requirements` are present in config schema but currently not fully enforced in runtime.
- Server capabilities are already explicit in code/config.
- Service capabilities are still emerging; today some of that intent is represented through YAML groups and service-type interfaces.

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
- Services are attached to a bundle and therefore run on a specific compute/server.
- A first-class service capability model is a likely next architectural step; current services already express parts of that through configs and typed interfaces.
- Each service should expose `get_secret()` returning access-relevant credentials/details (user/password/endpoint/etc.).
