# Architecture Notes For Coding Agents

Use this when changing core MLOX behavior.

## Mental Model

MLOX is a configuration-driven control plane:

1. YAML configs describe service/server metadata and `build.class_name`.
2. `mlox/config.py` loads built-in configs and Python entry-point plugins.
3. `MloxSession` owns project metadata, secret manager, and infrastructure.
4. `Infrastructure` owns the project topology: bundles, servers, and services.
5. Application use-cases in `mlox/application/use_cases/` should hold shared UI behavior.
6. CLI, TUI, and Streamlit should call shared use-cases instead of duplicating workflows.
7. Remote/system commands should route through `mlox/executors.py` and `mlox/execution/*`.

## High-Risk Areas

Treat these as high blast-radius:

- `mlox/config.py`: schema, YAML loading, plugin entry points, build class resolution.
- `mlox/session.py`: project loading, persistence, secret manager setup.
- `mlox/infra.py`: bundle/service topology, naming, port assignment, dependency lookup.
- `mlox/application/infrastructure_ops.py`: setup/teardown side effects.
- `mlox/ui/registry.py`: frontend handler lookup.

When changing one of these, check impact across CLI, TUI, Streamlit, saved project reload, and tests.

## Config Rules

- Preserve existing YAML keys unless intentionally migrating them.
- Keep plugin entry points working: `mlox.service_plugins` and `mlox.server_plugins`.
- Verify both service and server config loading when changing config code.
- Do not move frontend UI handler declarations into YAML.

## State Rules

- `MloxSession` is the runtime boundary.
- A session should always end with a secret manager instance, even if only the in-memory fallback is available.
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
