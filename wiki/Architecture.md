# MLOX Architecture — Human Contributor Guide

> **Source:** [`docs/ARCHITECTURE_HUMANS.md`](https://github.com/BusySloths/mlox/blob/main/docs/ARCHITECTURE_HUMANS.md)  
> A practical, contributor-first map of the MLOX codebase.

---

## Contents

1. [Fast Orientation](#1-fast-orientation)
2. [Setup, Tests, and Repo Surroundings](#2-setup-tests-and-repo-surroundings)
3. [Main Library Architecture](#3-main-library-architecture-mlox)
4. [Core Runtime Data Model](#4-core-runtime-data-model)
5. [Secret Manager Model](#5-secret-manager-model)
6. [Service Lifecycle and Execution Model](#6-service-lifecycle-and-execution-model)
7. [Design Notes and Current Limitations](#7-design-notes--current-limitations)
8. [Backend Abstraction](#8-backend-abstraction)
9. [Services and Servers — Authoring Conventions](#9-services-and-servers--authoring-conventions)

---

## 1. Fast Orientation

MLOX is a Python project that manages MLOps infrastructure through **three user interfaces**:

| Interface | Entry Point |
|-----------|------------|
| **CLI** | [`mlox/cli/app.py`](https://github.com/BusySloths/mlox/blob/main/mlox/cli/app.py) + [`mlox/cli/commands/`](https://github.com/BusySloths/mlox/blob/main/mlox/cli/commands/) |
| **TUI** (terminal UI) | [`mlox/tui/`](https://github.com/BusySloths/mlox/blob/main/mlox/tui/) |
| **Web App** (Streamlit) | [`mlox/view/`](https://github.com/BusySloths/mlox/blob/main/mlox/view/) |

The current CLI architecture routes through a thin application layer before it reaches the core runtime objects:

| Object | File | Role |
|--------|------|------|
| Application facade | [`mlox/application/facade.py`](https://github.com/BusySloths/mlox/blob/main/mlox/application/facade.py) | Loads/caches session context and dispatches use-cases |
| Use-case modules | [`mlox/application/use_cases/`](https://github.com/BusySloths/mlox/blob/main/mlox/application/use_cases/) | Session-based application actions grouped by domain |
| `MloxSession` | [`mlox/session.py`](https://github.com/BusySloths/mlox/blob/main/mlox/session.py) | Project/session state and persistence |
| `Infrastructure` | [`mlox/infra.py`](https://github.com/BusySloths/mlox/blob/main/mlox/infra.py) | Servers, bundles, services for a project |

```text
CLI (`mlox/cli/app.py` + `mlox/cli/commands/*`)
    └─► `mlox/application/facade.py`
          └─► `mlox/application/use_cases/*`
                └─► `MloxSession`
                      └─► `Infrastructure`

YAML configs are loaded through `mlox/config.py` into that flow.
```

---

## 2. Setup, Tests, and Repo Surroundings

### Task Runner

The project uses **Go Task** (`task`) as its task runner. The main configuration lives in [`taskfile.dist.yml`](https://github.com/BusySloths/mlox/blob/main/taskfile.dist.yml).

Key tasks:

| Task | Purpose |
|------|---------|
| `task first:steps` | Bootstrap the dev environment (conda env `mlox-dev`, Python 3.12.5) |
| `task dev:env:create` | Create the conda environment |
| `task ui:streamlit` | Launch the Streamlit web UI |
| `task ui:cli` | Launch the CLI |
| `task ui:textual:terminal` | Launch the TUI |
| `task tests:unit:run` | Run unit tests (fast, no external deps) |
| `task tests:integration:run` | Run integration tests (requires Multipass VMs) |
| `task docker:up` / `docker:down` | Spin up/down the local Docker stack |
| `task vm:start` | Start a Multipass test VM |

### Tests

| Suite | Location | Requirements |
|-------|----------|-------------|
| Unit tests | [`tests/unit/`](https://github.com/BusySloths/mlox/blob/main/tests/unit/) | Environment only |
| Integration tests | [`tests/integration/`](https://github.com/BusySloths/mlox/blob/main/tests/integration/) | Multipass VMs |

### Top-Level Directory Map

| Directory | Purpose |
|-----------|---------|
| [`examples/`](https://github.com/BusySloths/mlox/blob/main/examples/) | User-oriented usage snippets (OTel, MLflow tracking, DAG templates) |
| [`docs/`](https://github.com/BusySloths/mlox/blob/main/docs/) | Project documentation |
| [`scripts/`](https://github.com/BusySloths/mlox/blob/main/scripts/) | Experimental/hacky area — not a stable architecture reference |
| [`website/`](https://github.com/BusySloths/mlox/blob/main/website/) | Astro-based landing page |

### Documentation and Packaging

- **pdoc** generates the [API docs](https://busysloths.github.io/mlox/mlox.html) published to GitHub Pages.
- The package is published to **PyPI** as `busysloths-mlox` (`pyproject.toml` + deploy workflow).

---

## 3. Main Library Architecture (`mlox/`)

```
mlox/
├── application/    # facade + session-based use_cases
├── cli/            # Typer CLI package (root app + command modules)
├── services/       # 20+ deployable ML services (one directory each)
├── servers/        # Native and Ubuntu/SSH backends
├── tui/            # Textual terminal UI
├── view/           # Streamlit web UI
├── session.py      # Runtime state & persistence
├── infra.py        # Service/server graph
├── config.py       # YAML loading + plugin entry-point discovery
├── execution/      # backend/system execution helpers
├── executors.py    # remote task executor layer used by services/servers
└── assets/         # Outdated scripts/assets (not canonical)
```

### Configuration-Driven Building

Services and servers are built from **YAML configurations** loaded through [`mlox/config.py`](https://github.com/BusySloths/mlox/blob/main/mlox/config.py):

| YAML field | Purpose |
|------------|---------|
| `build.class_name` | Maps a config to its Python implementation class |
| `ports` | Declares intended port bindings (remappable at setup time) |
| `groups` | Partly descriptive; some map to functional classes (e.g., `git`) |
| `ui` | Controls how the service appears in the interfaces |
| `requirements` | Declares service dependencies (not yet fully enforced at runtime) |

Plugin loading is also wired in `config.py` via **entry-point discovery**.

---

## 4. Core Runtime Data Model

### `MloxSession` — Central Entry Point

[`mlox/session.py`](https://github.com/BusySloths/mlox/blob/main/mlox/session.py)

`MloxSession` is the main runtime object. It:

- Loads or creates a project
- Wires the secret manager
- Loads and saves the project infrastructure

### `Infrastructure` — Active Project Topology

[`mlox/infra.py`](https://github.com/BusySloths/mlox/blob/main/mlox/infra.py)

`Infrastructure` holds one project's server bundles and services for a given session.

### Persistent Storage

- Runtime structures are **dataclass-based** and serialized to JSON-compatible dicts.
- Project and infrastructure data are stored through a **secret manager** abstraction.
- A session always has a secret manager configured (falls back to in-memory if no external store is available).

---

## 5. Secret Manager Model

MLOX supports multiple secret-manager backends:

| Type | Implementation |
|------|---------------|
| In-memory (dev/testing) | `InMemorySecretManager` |
| File-based lightweight | `TinySecretManager` |
| OpenBao (open-source Vault) | [`mlox/services/openbao/`](https://github.com/BusySloths/mlox/blob/main/mlox/services/openbao/) |
| GCP Secret Manager | [`mlox/services/gcp/secret_manager.py`](https://github.com/BusySloths/mlox/blob/main/mlox/services/gcp/secret_manager.py) |

`MloxProject` metadata stores which secret manager class is used and how to reconnect to it across sessions.

---

## 6. Service Lifecycle and Execution Model

### Shared Control Flow

The CLI now goes through `mlox/cli/commands/*` -> `mlox/application/facade.py` -> `mlox/application/use_cases/*` -> `MloxSession` -> `Infrastructure`.

TUI and Web UI must preserve the same session/infrastructure behavior even where they do not yet share the exact same presentation-layer wiring.

### Executors Handle System Calls

All low-level command execution is routed through task executors:

- [`mlox/executors.py`](https://github.com/BusySloths/mlox/blob/main/mlox/executors.py) — base executor logic
- Server-specific executors (e.g., `UbuntuTaskExecutor`) — remote shell operations

> ⚠️ **Architectural rule:** operational system calls must _not_ be scattered inside service logic. Always route through executors.

### Port Assignment

- YAML config declares the **intended ports** for a service.
- During infrastructure setup, ports can be **remapped** to avoid collisions.

---

## 7. Design Notes & Current Limitations

| Area | Notes |
|------|-------|
| `mlox/scheduler.py` | Effectively legacy/obsolete — not part of the active architecture |
| `mlox/application/facade.py` | Thin stateless facade that loads/caches session context and dispatches to `application/use_cases/*` |
| `mlox/application/infrastructure_ops.py` | Orchestration helpers used by session-based use-cases for setup/teardown-style side effects |
| YAML `requirements` | Present in the config schema but **not yet fully enforced** at runtime |
| YAML `groups` | Partly descriptive today; some map to functional classes (e.g., `git`), but this is not yet fully consistent |

---

## 8. Backend Abstraction

MLOX is **backend-agnostic** at the architecture level.

| Backend | Status |
|---------|--------|
| Native (direct SSH) | ✅ Stable |
| Docker | ✅ Stable |
| Kubernetes | ✅ Stable |

The design aims to make adding additional backends (e.g., new Kubernetes distributions or custom platforms) relatively straightforward.

---

## 9. Services and Servers — Authoring Conventions

Each service lives in its own directory under `mlox/services/` and follows these conventions:

- **YAML config** — defines service identity, ports, groups, requirements, and build class
- **Backend-specific implementation classes** — one per supported backend (native, docker, k8s)
- **Deployment files** — e.g., Docker Compose templates bundled with the service
- **`client.py`** _(optional)_ — helper client so users can consume the service from Python code
- **`get_secret()`** — every service should expose this method, returning access credentials (user, password, endpoint, etc.)

### Service Dependencies

Services can depend on other services:

- Dependency UUIDs are stored on service objects.
- Dependent services are resolved via helper methods (e.g., the `get_dependent_service` pattern).

### Server Conventions

Servers also have MLOX YAML configs and follow the same configuration-driven model.

---

## See Also

- [Home](Home) — Project overview and navigation
- [`docs/ARCHITECTURE_AGENTS.md`](https://github.com/BusySloths/mlox/blob/main/docs/ARCHITECTURE_AGENTS.md) — High-risk areas and invariants (for AI agents)
- [`docs/INSTALLATION.md`](https://github.com/BusySloths/mlox/blob/main/docs/INSTALLATION.md) — Setup guide
- [`CONTRIBUTING.md`](https://github.com/BusySloths/mlox/blob/main/CONTRIBUTING.md) — How to contribute
