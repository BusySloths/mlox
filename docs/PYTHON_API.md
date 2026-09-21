# Python API

`ProjectWorkspace` is the supported public runtime API for opening and changing an
MLOX project. It owns the persistence boundary: successful application mutations
are committed once, while failed mutations reload the last persisted state.

```python
from mlox.project import ProjectWorkspace

workspace = ProjectWorkspace.open("demo.mlox", password)
result = workspace.setup_server(ip="10.0.0.5")
if not result.success:
    raise RuntimeError(result.message)
```

## Supported surface

The compatibility-supported SDK surface consists of:

- project lifecycle: `open`, `create`, `can_open`, `commit`, and `reload`;
- project metadata and the read-only `infrastructure`, `path`, and `secrets`
  properties;
- knowledge-base entry methods;
- secret-manager listing, probing, and selection methods;
- server operations: list, add, setup, health, teardown, and key export;
- service operations: list, add, setup, health, lifecycle, rename, and logs;
- model listing and deployment; and
- server and service configuration listing.

Methods prefixed with an underscore are internal. `add_server_from_config`,
`add_service_from_config`, `import_secrets`, and `project_created` are frontend or
project-loading integration helpers. They remain available to existing callers but
are not the preferred SDK entrypoints.

## Mutation behavior

Methods that change project infrastructure execute through the workspace mutation
boundary. A successful result is persisted atomically. A failed result or unexpected
exception restores the last persisted workspace state. Callers should therefore use
workspace operations instead of invoking functions from `mlox.application.use_cases`
with internal `WorkspaceState` objects.

Direct metadata assignment is intentionally explicit and requires `commit()`:

```python
workspace.descr = "Shared model-serving environment"
workspace.commit()
```

Use `reload()` to discard uncommitted in-memory metadata changes.

## Results

Application methods return `OperationResult`, containing `success`, `code`,
`message`, and optional `data`. Result payloads are currently dictionaries whose
shape depends on the operation. Typed payload contracts are the next API-hardening
step; callers should prefer documented keys and avoid depending on live internal
objects found in legacy payloads.

## Compatibility

Within a release line, supported method names, parameters, parameter kinds, and
defaults are treated as compatibility contracts. New optional parameters may be
added. Removing or renaming methods and parameters, changing positional versus
keyword-only behavior, or changing runtime payload representation requires an
explicit migration and release note.
