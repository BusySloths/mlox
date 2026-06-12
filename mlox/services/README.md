# Services

This package contains deployable services and external connectors managed by
MLOX.

## Structure

Each service directory may contain:

- A concrete `AbstractService` implementation.
- One or more `mlox*.yaml` configuration definitions.
- Compose files, manifests, scripts, and client helpers.
- Service-specific documentation where needed.

## Workflow

Configuration loading resolves `build.class_name`, instantiates the service, and
attaches it to an infrastructure bundle. Application use cases run setup,
status, and teardown through the service and its server executor.

## System Role

Service classes own provider-specific behavior and persisted runtime state.
Frontend panels belong in `mlox.view.services` or `mlox.tui.services`.

