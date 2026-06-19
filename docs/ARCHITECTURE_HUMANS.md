# MLOX Architecture

This is the contributor-facing map of the current codebase.

## Runtime Shape

MLOX models the infrastructure around an ML/AI product as a connected topology of servers, services, secrets, and dependencies. It exposes three local interfaces:

- CLI: `mlox/cli/`
- TUI: `mlox/tui/`
- Streamlit web UI: `mlox/view/`

Those interfaces should stay thin. Shared behavior belongs in the application layer.

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
WorkspaceState
        |
        v
Infrastructure -> Bundle = one server/compute + deployed services
        |
        v
executors + backend adapters
```

## Important Modules

- `mlox/project/state.py`: internal `WorkspaceState` for metadata and infrastructure.
- `mlox/project/repository.py`: internal `SqlCipherRepository` for SQLCipher persistence.
- `mlox/infra.py`: topology model containing bundles, servers, and services.
- `mlox/application/use_cases/`: project-based server, service, and model actions.
- `mlox/project/workspace.py`: public `ProjectWorkspace` API and mutation boundary.
- `mlox/config.py`: YAML and plugin config loading.
- `mlox/executors.py` and `mlox/execution/`: command execution and backend helpers.
- `mlox/ui/registry.py`: frontend handler lookup for Streamlit/TUI-specific setup panels.

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

A bundle contains one compute/server and the services deployed onto it. Servers advertise capabilities such as `git`, `docker`, `kubernetes`, `firewall`, or native execution support. Services declare their intended capabilities in config, but that model is still evolving.

Rules for new service/server work:

- Add or update the MLOX YAML config.
- Keep deployment assets beside the service/server implementation.
- Route remote/system work through executors instead of ad-hoc shell calls in UI code.
- Expose access details through `get_secret()` when the service has credentials or endpoints.
- Store service dependencies by UUID and resolve them through infrastructure/session helpers.
- Keep Streamlit/TUI setup panels in frontend modules, registered through `mlox/ui/registry.py`.

## Current Limitations

- `requirements` in YAML are parsed but not fully enforced at runtime.
- Service capabilities are useful metadata but not yet a complete placement policy.
- `Infrastructure` contains queries, serialization, and runtime hydration only.
- UI handler plugin registration is not yet part of the documented external plugin API.

## Development Commands

Use Task as the command index:

```bash
task
task first:steps
task tests:unit:run
task tests:integration:run
task tests:integration:k8s
task docker:up
task docker:down
```

Unit tests live in `tests/unit/`. Integration tests live in `tests/integration/`
and require Multipass. Kubernetes integration tests are selected with
`task tests:integration:k8s`, which runs tests marked with both `integration`
and `kubernetes`.
