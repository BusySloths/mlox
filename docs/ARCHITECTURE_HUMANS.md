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
ProjectApplication
        |
        v
ProjectSession
        |
        v
ProjectAggregate
        |
        v
Infrastructure -> Bundle = one server/compute + deployed services
        |
        v
executors + backend adapters
```

## Important Modules

- `mlox/project/aggregate.py`: `ProjectAggregate`, the aggregate root for metadata and infrastructure.
- `mlox/session.py`: `ProjectSession`, the SQLCipher persistence, migration, and secrets boundary.
- `mlox/infra.py`: topology model containing bundles, servers, and services.
- `mlox/application/use_cases/`: project-based server, service, and model actions.
- `mlox/application/facade.py`: stateful `ProjectApplication` that commits successful mutations and reloads failed ones.
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

`ProjectSession` loads a complete `ProjectAggregate`, exposes project-backed secrets, and
atomically commits metadata and infrastructure. `ProjectApplication` owns one
session and is the preferred API for mutations. Use cases receive a `ProjectAggregate`;
they do not know about persistence.

Supported secret manager paths include:

- in-memory fallback
- TinySecretManager
- OpenBao
- GCP Secret Manager

Runtime objects are serialized to JSON-compatible dictionaries and stored through the configured secret manager.

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
task docker:up
task docker:down
```

Unit tests live in `tests/unit/`. Integration tests live in `tests/integration/` and require Multipass.
