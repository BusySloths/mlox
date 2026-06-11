# Architecture Notes For Coding Agents

Use this when changing core MLOX behavior.

## Mental Model

MLOX is a configuration-driven system for managing a connected topology of ML/AI servers, services, secrets, and dependencies:

1. YAML configs describe service/server metadata and `build.class_name`.
2. `mlox/config.py` loads built-in configs and Python entry-point plugins.
3. `ProjectAggregate` is the aggregate root for metadata and `Infrastructure`.
4. `ProjectSession` owns SQLCipher persistence and embedded secrets.
5. `ProjectApplication` owns one session and is the public mutation boundary.
6. Application use-cases accept `ProjectAggregate` and never persist directly.
7. CLI, TUI, and Streamlit should call `ProjectApplication` instead of mutating topology directly.
8. Remote/system commands should route through `mlox/executors.py` and `mlox/execution/*`.

## High-Risk Areas

Treat these as high blast-radius:

- `mlox/config.py`: schema, YAML loading, plugin entry points, build class resolution.
- `mlox/session.py`: project loading, atomic persistence, secret access, migrations.
- `mlox/infra.py`: bundle/service topology, naming, port assignment, dependency lookup.
- `mlox/application/facade.py`: stateful application commit and rollback behavior.
- `mlox/application/use_cases/`: setup/teardown and domain mutations.
- `mlox/ui/registry.py`: frontend handler lookup.

When changing one of these, check impact across CLI, TUI, Streamlit, saved project reload, and tests.

## Config Rules

- Preserve existing YAML keys unless intentionally migrating them.
- Keep plugin entry points working: `mlox.service_plugins` and `mlox.server_plugins`.
- Verify both service and server config loading when changing config code.
- Do not move frontend UI handler declarations into YAML.

## State Rules

- `ProjectApplication` is the mutation boundary; `ProjectSession` is the persistence boundary.
- Successful mutations commit once. Failed mutations reload the aggregate.
- A session exposes the project-backed secret adapter; production project storage must fail closed when SQLCipher is unavailable.
- Metadata and infrastructure must be stored in one transaction.
- Persisted objects must remain JSON-compatible.
- Service dependencies should be stable by UUID, not by display name.

## Infrastructure Rules

- A bundle is one compute/server plus attached services.
- Effective ports may differ from YAML defaults because MLOX can remap ports to avoid collisions.
- Do not assume service capability metadata is complete enough for all placement decisions.
- Keep domain-like state changes separate from side-effectful setup work where practical.

## Service/Server Authoring Checklist

- Provide a config under `mlox/services/**/mlox*.yaml` or `mlox/servers/**/mlox-server*.yaml`.
- Point `build.class_name` to a concrete implementation class.
- Keep compose files, manifests, scripts, and client helpers near the service/server.
- Use executors for commands on target machines.
- Return credentials/endpoints from `get_secret()` where applicable.
- Register custom frontend setup/settings handlers in frontend modules through `mlox/ui/registry.py`.

## Verification

Prefer focused checks first:

```bash
task tests:unit:run
```

For config changes, also verify service/server loading with the existing unit tests under `tests/unit/test_service_configs.py`, `tests/unit/test_server_configs.py`, and `tests/unit/test_config_plugins.py`.

Integration tests require Multipass:

```bash
task tests:integration:run
task tests:integration:cleanup
```
