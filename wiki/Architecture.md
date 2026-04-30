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

The shared architecture is centered on a session container and session-based use-cases:

| Object | File | Role |
|--------|------|------|
| Use-case modules | [`mlox/application/use_cases/`](https://github.com/BusySloths/mlox/blob/main/mlox/application/use_cases/) | Session-based application actions that should be shared by all UIs |
| `MloxSession` | [`mlox/session.py`](https://github.com/BusySloths/mlox/blob/main/mlox/session.py) | Project/session container holding metadata, secret manager, and infrastructure |
| `Infrastructure` | [`mlox/infra.py`](https://github.com/BusySloths/mlox/blob/main/mlox/infra.py) | Project topology made of bundles, compute, and services |
| Application facade | [`mlox/application/facade.py`](https://github.com/BusySloths/mlox/blob/main/mlox/application/facade.py) | Current stateless adapter used mainly by the CLI and callers that need session loading/caching |

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
├── tui/            # Textual terminal UI + TUI-specific UI handlers
├── ui/             # frontend UI handler registry
├── view/           # Streamlit web UI + Streamlit-specific UI handlers
├── session.py      # Runtime state & persistence
├── infra.py        # Service/server graph
├── config.py       # YAML loading + plugin discovery + UI handler lookup
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
| `capabilities` | Declares backend/server capability metadata when needed |
| `requirements` | Declares service dependencies (not yet fully enforced at runtime) |

Plugin loading is also wired in `config.py` via **entry-point discovery**.

Frontend-specific UI handlers are no longer modeled in YAML. They live in frontend modules and are resolved through `mlox/ui/registry.py` by config ID, frontend namespace, and function name.

---

## 4. Core Runtime Data Model

### `MloxSession` — Central Entry Point

[`mlox/session.py`](https://github.com/BusySloths/mlox/blob/main/mlox/session.py)

`MloxSession` is the main runtime object. It:

- Loads or creates a project
- Wires the secret manager
- Loads and saves the project infrastructure
- Gives the runtime one place to find project metadata, secrets, and topology

### `Infrastructure` — Active Project Topology

[`mlox/infra.py`](https://github.com/BusySloths/mlox/blob/main/mlox/infra.py)

`Infrastructure` holds one project's server bundles and services for a given session.

### `Bundle` — One Compute plus Its Services

`Bundle` is the operational unit inside `Infrastructure`:

- one bundle contains one compute/server object
- that compute advertises capabilities such as `git`, `docker`, `kubernetes`, `firewall`, or local/native runtime support
- the same bundle also contains the services deployed onto that compute

This makes `Infrastructure` the topology root for "what runs where".

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

In practice, `MloxSession` is the persistence boundary around `Infrastructure`, and the secret manager is the encrypted key-value store behind that boundary.

---

## 6. Service Lifecycle and Execution Model

### Shared Control Flow

The intended control flow is:

- UI layer (`cli`, `tui`, `view`, future UIs)
- shared application layer (`mlox/application/use_cases/*`)
- session container (`MloxSession`)
- topology root (`Infrastructure`)

The CLI currently reaches that shared layer through `mlox/application/facade.py`. TUI and Streamlit should converge on the same use-cases so behavior stays aligned across interfaces.

`Infrastructure` is primarily the topology model, but it still exposes compatibility wrappers that delegate some lifecycle work into `mlox/application/infrastructure_ops.py`.

For custom setup/settings panels, the ownership moved to the frontend packages. Built-in Streamlit and TUI handlers are bootstrapped into `mlox/ui/registry.py`, which keeps deployable configs UI-agnostic and creates a later extension point for plugin UI contributions.

### Executors Handle System Calls

Anything that executes on a compute/server should route through the execution layer:

- [`mlox/executors.py`](https://github.com/BusySloths/mlox/blob/main/mlox/executors.py) — task executor entry point
- [`mlox/execution/`](https://github.com/BusySloths/mlox/blob/main/mlox/execution/) — backend/system helper modules
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
| `mlox/application/use_cases/*` | Important shared session-based application layer; keep growing behavior here instead of reintroducing broad operations modules |
| `mlox/application/facade.py` | Thin stateless adapter that loads/caches session context and dispatches to `application/use_cases/*` |
| `mlox/application/infrastructure_ops.py` | Orchestration helpers used by session-based use-cases for setup/teardown-style side effects |
| YAML `requirements` | Present in the config schema but **not yet fully enforced** at runtime |
| UI registration | Frontend-owned via `mlox/ui/registry.py`; keep UI definitions out of service/server YAML |
| Server capabilities | Already explicit in code/config |
| Service capabilities | Still emerging; today some of that intent is represented through YAML groups and service-type interfaces |

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
- **Frontend-specific UI handlers** — live in frontend packages and register through `mlox/ui/registry.py`
- **`client.py`** _(optional)_ — helper client so users can consume the service from Python code
- **`get_secret()`** — every service should expose this method, returning access credentials (user, password, endpoint, etc.)

### Service Dependencies

Services can depend on other services:

- Dependency UUIDs are stored on service objects.
- Dependent services are resolved via helper methods (e.g., the `get_dependent_service` pattern).
- Services are attached to a bundle and therefore run on a specific compute/server.
- A first-class service capability model is a likely next architectural step; current services already express parts of that through configs and typed interfaces.

### Server Conventions

Servers also have MLOX YAML configs and follow the same configuration-driven model.

Today the built-in registry bootstraps handlers from `mlox.view.services`, `mlox.view.servers.ubuntu`, and `mlox.tui.services`. Plugin-provided deployable configs are supported through entry points; plugin-provided UI handlers are a likely next step, but not yet part of the documented plugin API.

---

## See Also

- [Home](Home) — Project overview and navigation
- [`docs/ARCHITECTURE_AGENTS.md`](https://github.com/BusySloths/mlox/blob/main/docs/ARCHITECTURE_AGENTS.md) — High-risk areas and invariants (for AI agents)
- [`docs/INSTALLATION.md`](https://github.com/BusySloths/mlox/blob/main/docs/INSTALLATION.md) — Setup guide
- [`CONTRIBUTING.md`](https://github.com/BusySloths/mlox/blob/main/CONTRIBUTING.md) — How to contribute
