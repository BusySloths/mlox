# MLOX Architecture

This is the **single entry point** into the MLOX codebase, for both humans and
coding agents. Read `docs/DOCTRINE.md` for **status, roadmap, and binding
decisions** (including the deprecated Streamlit UI). The generated service/server
catalog lives in `docs/SERVICES_CATALOG.md`. This file covers **architecture and
code invariants only** — do not restate doctrine or catalog facts here.

> **Scope is broader than "MLOps tool".** Nothing in the plugin/config mechanism
> is ML-specific — the same YAML + capability-ABC pattern could host groupware or
> any self-hosted service. Read MLOX as a general self-hosted infrastructure
> control plane that currently specializes in MLOps (closer in ambition to a
> self-hosted PaaS like Railway/Coolify than to a narrow MLOps competitor).

> **Do not invest in `mlox/view/` or `mlox/app.py`.** The Streamlit web UI is
> being phased out into a plugin repo; the TUI and CLI are the primary
> interfaces. Treat web-UI changes as maintenance-only. (ADR in `docs/DOCTRINE.md`.)

## Runtime Shape

MLOX models the infrastructure around an ML/AI product as a connected topology of servers, services, secrets, and dependencies. It exposes CLI (`mlox/cli/`) and TUI (`mlox/tui/`) as its primary interfaces.

Those interfaces should stay thin. Shared behavior belongs in the application layer.

```text
CLI / TUI
        |
        v
ProjectWorkspace
        |
        v
internal WorkspaceState + SqlCipherRepository
        |
        v
WorkspaceState
        |
        v
Infrastructure -> Bundle = one server/compute + deployed services
        |
        v
executors + backend adapters
```

## Three-tier Model

1. **Servers** — physical/VM hosts (`mlox/server.py`, `mlox/servers/`).
2. **Backend** — how a server executes work: native, Docker, Kubernetes, local,
   connector (capability mixins like `AbstractDockerServer`, `AbstractKubernetesServer`).
3. **Services** — what runs on top (`mlox/service.py`, `mlox/services/*`; the count
   changes over time — see the generated `docs/SERVICES_CATALOG.md`).

A `Bundle` (`mlox/infra.py`) ties one server to its deployed services;
`Infrastructure` is the full topology graph, queryable by capability/backend/tag.

- **Plugin model:** every service/server is a YAML config (`mlox*.yaml` /
  `mlox-server*.yaml`) declaring metadata, ports, capabilities, and
  `build.class_name`. Third-party plugins register via `mlox.service_plugins` /
  `mlox.server_plugins` entry points (see `docs/PLUGIN_CONFIGS.md`).
- **Capability ABCs, not type-switch branching:** behavior comes from capability
  ABCs (Docker, Kubernetes, Native, Firewall, Git, Health, ...) — a
  service/server's abilities are determined by which mixins it implements.

## Important Modules

- `mlox/project/state.py`: internal `WorkspaceState` for metadata and infrastructure.
- `mlox/project/repository.py`: internal `SqlCipherRepository` for SQLCipher persistence.
- `mlox/infra.py`: topology model containing bundles, servers, and services.
- `mlox/application/use_cases/`: project-based server, service, and model actions.
- `mlox/project/workspace.py`: public `ProjectWorkspace` API and mutation boundary.
- `mlox/config.py`: YAML and plugin config loading.
- `mlox/executors.py` and `mlox/execution/`: command execution and backend helpers.
- `mlox/ui/registry.py`: frontend handler lookup for frontend-specific setup panels.

## Config Model

Built-in configs live under:

- `mlox/services/**/mlox*.yaml`
- `mlox/servers/**/mlox-server*.yaml`

Each config declares metadata, capabilities, requirements, ports, and `build.class_name`. `build.class_name` points to the Python class that implements the service or server.

Frontend UI handlers are not declared in YAML. They live in frontend modules and are registered through `mlox/ui/registry.py`.

External config plugins are loaded from Python entry points:

- `mlox.service_plugins`
- `mlox.server_plugins`

See `docs/PLUGIN_CONFIGS.md` for the minimal plugin contract.

## State And Persistence

`ProjectWorkspace` loads internal workspace state, exposes project-backed secrets,
and atomically commits metadata and infrastructure. It is the only public project
runtime object. Use cases receive `WorkspaceState`; they do not know about persistence.

Exactly one secret manager is active per workspace. Supported providers include:

- embedded SQLCipher project storage
- TinySecretManager
- OpenBao
- GCP Secret Manager

The active provider is persisted as either `embedded` or a secret-manager service
UUID. Unavailable external providers remain selected; there is no automatic
fallback. Provider changes copy and verify secrets before the pointer is committed.

SQLModel is intentionally deferred. The infrastructure graph remains behavior-heavy
and polymorphic, while the JSON snapshot is still authoritative. Reconsider separate
SQLModel persistence records when partial queries, concurrent updates, or PostgreSQL
become active requirements.

## Services, Servers, And Execution

A bundle contains one compute/server and the services deployed onto it. Servers advertise capabilities such as `git`, `docker`, `kubernetes`, `firewall`, `health`, or native execution support. Services declare their intended capabilities in config, including `health` when they provide a richer live probe than the generic lifecycle state.

- **Execution abstraction is not "SSH-only".** `mlox/execution/base.py`
  (`TaskRunnerABC`, `ExecutionRecorder`) is execution-target-agnostic by design.
  The current concrete implementation, `UbuntuTaskExecutor` (`mlox/executors.py`),
  is Fabric/SSH-based, but the ABC boundary anticipates local and embedded
  execution too — don't assume "execution == remote SSH".
- **Secrets:** route access credentials/endpoints through `get_secret()`.
- Route system operations through executors; never scatter shell calls in UI code.

## High-Risk Areas

Treat these as high blast-radius; check impact across CLI, TUI, saved project
reload, and tests when changing them:

- `mlox/config.py` — schema, YAML loading, plugin entry points, build class resolution.
- `mlox/project/repository.py` — project loading, atomic persistence, secret storage.
- `mlox/infra.py` — bundle/service topology, naming, port assignment, dependency lookup.
- `mlox/project/workspace.py` — public API, commit, and rollback behavior.
- `mlox/application/use_cases/` — setup/teardown and domain mutations.
- `mlox/ui/registry.py` — frontend handler lookup.

## Invariants

### Config rules

- Preserve existing YAML keys unless intentionally migrating them.
- Keep plugin entry points working: `mlox.service_plugins` and `mlox.server_plugins`.
- Verify both service and server config loading when changing config code.
- Do not move frontend UI handler declarations into YAML.

### State rules

- `ProjectWorkspace` is the public mutation and explicit-commit boundary.
- Successful application mutations commit once. Failed mutations reload workspace state.
- `workspace.secrets` exposes the single selected provider. Unavailable external
  providers must remain selected rather than falling back to embedded storage.
- Block removal of the active secret-manager service or its server.
- Metadata and infrastructure must be stored in one transaction.
- Persisted objects must remain JSON-compatible.
- Service dependencies should be stable by UUID, not by display name.

### Infrastructure rules

- A bundle is one compute/server plus attached services.
- Effective ports may differ from YAML defaults because MLOX can remap ports to
  avoid collisions.
- Do not assume service capability metadata is complete enough for all placement
  decisions.
- Keep domain-like state changes separate from side-effectful setup work where practical.

### Service/server authoring checklist

- Provide a config under `mlox/services/**/mlox*.yaml` or `mlox/servers/**/mlox-server*.yaml`.
- Point `build.class_name` to a concrete implementation class.
- Keep compose files, manifests, scripts, and client helpers near the service/server.
- Use executors for commands on target machines; don't scatter shell calls in UI code.
- Route health checks through the application use cases so the reported state is
  normalized and persisted before the UI refreshes.
- Return credentials/endpoints from `get_secret()` where applicable.
- Store service dependencies by UUID and resolve them through infrastructure/session helpers.
- Register custom frontend setup/settings handlers in frontend modules through
  `mlox/ui/registry.py`.

## Current Limitations

- `requirements` in YAML are parsed but not fully enforced at runtime.
- Service capabilities are useful metadata and UI affordances but not yet a complete placement policy.
- `Infrastructure` contains queries, serialization, and runtime hydration only.
- UI handler plugin registration is not yet part of the documented external plugin API.

These are tracked as roadmap items in `docs/DOCTRINE.md`.

## Verification

Prefer focused checks first:

```bash
task tests:unit:run
```

For config changes also verify service/server loading with
`tests/unit/test_service_configs.py`, `tests/unit/test_server_configs.py`, and
`tests/unit/test_config_plugins.py`. Integration tests require Multipass
(`task tests:integration:run`); `task tests:integration:k8s` runs only tests
marked both `integration` and `kubernetes` (provisions a Multipass/k3s backend).

Other useful tasks (see `task file` for the full index):

```bash
task
task first:steps
task docker:up
task docker:down
```
