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
`message`, and optional `data`. `OperationResult` is generic, and public server,
service, model, and configuration operations declare `TypedDict` payload contracts
from `mlox.application.payloads`. Runtime payloads remain dictionaries for backward
compatibility.

Some mutation results still contain live `Bundle`, `AbstractServer`, or
`AbstractService` references for existing UI callers. Those contracts are explicitly
marked as internal payloads. External adapters must serialize stable fields rather
than returning these objects directly.

## CLI exposure

The CLI exposes a deliberate subset of this API through domain manifests under
`mlox/cli/specifications/`. A specification module such as
`specifications/server.py` is a declarative CLI contract: it selects workspace
methods and describes command names, arguments versus options, aliases, input
transforms, help text, and result renderers. It is analogous to a reusable command
recipe, not to an MLOX server or service YAML template.

The matching module under `mlox/cli/commands/` is the executable Typer wiring. For
example, `commands/server.py` creates the server command group and registers the
recipes from `specifications/server.py`. The shared generator reads parameter types
and defaults from the selected `ProjectWorkspace` methods. The aggregate
`specifications` package re-exports every domain manifest for future discovery by
documentation or agent adapters.

Adding a straightforward CLI command therefore requires:

1. a typed `ProjectWorkspace` method returning `OperationResult`;
2. an explicit `WorkspaceCommand` entry in the appropriate manifest; and
3. a renderer that converts its result payload to terminal output.

Manifest entries are validated against workspace signatures when the CLI is
imported. Methods are never exposed merely because they exist. Commands that parse
compound values, coordinate several operations, or need custom output flow should
remain handwritten adapters; model deployment is the current example.

## Compatibility

Within a release line, supported method names, parameters, parameter kinds, and
defaults are treated as compatibility contracts. New optional parameters may be
added. Removing or renaming methods and parameters, changing positional versus
keyword-only behavior, or changing runtime payload representation requires an
explicit migration and release note.
