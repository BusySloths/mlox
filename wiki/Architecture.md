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

MLOX models the infrastructure around an ML/AI product as a connected topology of servers, services, secrets, and dependencies. It exposes **three user interfaces**:

| Interface | Entry Point |
|-----------|------------|
| **CLI** | [`mlox/cli/app.py`](https://github.com/BusySloths/mlox/blob/main/mlox/cli/app.py) + [`mlox/cli/commands/`](https://github.com/BusySloths/mlox/blob/main/mlox/cli/commands/) |
| **TUI** (terminal UI) | [`mlox/tui/`](https://github.com/BusySloths/mlox/blob/main/mlox/tui/) |
| **Web App** (Streamlit) | [`mlox/view/`](https://github.com/BusySloths/mlox/blob/main/mlox/view/) |

The shared architecture is centered on a project aggregate and stateful application:

| Object | File | Role |
|--------|------|------|
| `ProjectApplication` | [`mlox/application/facade.py`](https://github.com/BusySloths/mlox/blob/main/mlox/application/facade.py) | Stateful public mutation API and commit boundary |
| Use-case modules | [`mlox/application/use_cases/`](https://github.com/BusySloths/mlox/blob/main/mlox/application/use_cases/) | Project-based server, service, and model operations |
| `ProjectSession` | [`mlox/session.py`](https://github.com/BusySloths/mlox/blob/main/mlox/session.py) | SQLCipher persistence and project-backed secrets |
| `ProjectAggregate` | [`mlox/project/aggregate.py`](https://github.com/BusySloths/mlox/blob/main/mlox/project/aggregate.py) | Aggregate root containing metadata and infrastructure |
| `Infrastructure` | [`mlox/infra.py`](https://github.com/BusySloths/mlox/blob/main/mlox/infra.py) | Project topology made of bundles, compute, and services |

```text
CLI     TUI     Streamlit Web UI     Other UIs
  \      |             |                /
   \     |             |               /
    +----+-------------+--------------+
                    |
                    v
              `ProjectApplication`
           shared mutation boundary
                    |
                    v
              `ProjectSession`
       SQLCipher persistence + secrets
             /                               \
            v                                 v
 embedded SQLCipher storage                `Infrastructure`
 (metadata + topology + secrets)      topology for one project
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
| [`wiki/`](https://github.com/BusySloths/mlox/blob/main/wiki/) | Source pages for the GitHub Wiki |
| [`scripts/`](https://github.com/BusySloths/mlox/blob/main/scripts/) | Development, recovery, and service-testing utilities |
| [`website/`](https://github.com/BusySloths/mlox/blob/main/website/) | Astro-based landing page |

### Documentation and Packaging

- **pdoc** generates the [API docs](https://busysloths.github.io/mlox/mlox.html) published to GitHub Pages.
- The package is published to **PyPI** as `busysloths-mlox` (`pyproject.toml` + deploy workflow).

---

## 3. Main Library Architecture (`mlox/`)

```
mlox/
├── application/    # Stateful application API and shared use cases
├── cli/            # Typer CLI package (root app + command modules)
├── execution/      # Backend and system execution helpers
├── project/        # Aggregate, SQLCipher repository, and secret adapter
├── servers/        # Local, connector, and Ubuntu compute backends
├── services/       # Deployable ML/AI services and integrations
├── tui/            # Textual terminal UI + TUI-specific UI handlers
├── ui/             # Frontend UI handler registry
├── view/           # Streamlit web UI + Streamlit-specific UI handlers
├── assets/         # Runtime templates and packaged assets
├── resources/      # Images and other static resources
├── session.py      # Runtime state & persistence
├── infra.py        # Service/server graph
├── config.py       # YAML loading + plugin discovery + UI handler lookup
└── executors.py    # Remote task executor layer used by services/servers
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

### `ProjectApplication` and `ProjectSession`

[`mlox/session.py`](https://github.com/BusySloths/mlox/blob/main/mlox/session.py)

`ProjectApplication` is the preferred runtime API. It:

- Opens an existing project or explicitly creates a new one
- Dispatches project-based use cases
- Commits successful mutations once
- Reloads the aggregate after failed mutations

`ProjectSession` is the lower-level persistence API. It loads and atomically saves
the complete `ProjectAggregate`, exposes project-backed secrets, and
supports explicit `commit()` and `reload()` calls.

### `Infrastructure` — Active Project Topology

[`mlox/infra.py`](https://github.com/BusySloths/mlox/blob/main/mlox/infra.py)

`Infrastructure` holds one project's server bundles and services. It provides
queries, serialization, config hydration, and service lookup binding, but no
application mutation wrappers.

### `Bundle` — One Compute plus Its Services

`Bundle` is the operational unit inside `Infrastructure`:

- one bundle contains one compute/server object
- that compute advertises capabilities such as `git`, `docker`, `kubernetes`, `firewall`, or local/native runtime support
- the same bundle also contains the services deployed onto that compute

This makes `Infrastructure` the topology root for "what runs where".

### Persistent Storage

- Runtime structures are **dataclass-based** and serialized to JSON-compatible dicts.
- Project metadata, infrastructure, and secrets are stored transactionally in an encrypted **SQLCipher** `.mlox` database.
- A session always exposes a secret-manager-compatible adapter backed by the active project database.

---

## 5. Secret Manager Model

MLOX supports multiple embedded SQLCipher storages:

| Type | Implementation |
|------|---------------|
| In-memory (dev/testing) | `InMemorySecretManager` |
| File-based lightweight | `TinySecretManager` |
| OpenBao (open-source Vault) | [`mlox/services/openbao/`](https://github.com/BusySloths/mlox/blob/main/mlox/services/openbao/) |
| GCP Secret Manager | [`mlox/services/gcp/secret_manager.py`](https://github.com/BusySloths/mlox/blob/main/mlox/services/gcp/secret_manager.py) |

The project database itself is the authoritative secret store. External secret
managers can be imported through `ProjectSession.import_secrets()`.

---

## 6. Service Lifecycle and Execution Model

### Shared Control Flow

The intended control flow is:

- UI layer (`cli`, `tui`, `view`, future UIs)
- shared application layer (`mlox/application/use_cases/*`)
- stateful application (`ProjectApplication`)
- persistence boundary (`ProjectSession`)
- topology root (`Infrastructure`)

CLI commands open a `ProjectApplication` per invocation. TUI and Streamlit retain
one application in runtime state. All three interfaces share the same use cases.

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
| `mlox/application/use_cases/*` | Project-based operations; persistence stays outside use cases |
| `mlox/application/facade.py` | Stateful `ProjectApplication` with commit/reload behavior |
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
