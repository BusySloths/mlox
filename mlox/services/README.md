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
Frontend panels belong in `mlox.tui.services`.


## Object storage contract

Services advertising `object_storage` implement `AbstractObjectStorageService`
and expose a client with `list_keys(bucket, prefix)`, `read_bytes(bucket, key)`,
and `write_bytes(bucket, key, data)`. These operate on existing buckets and
propagate provider errors. Existing provider-specific client methods remain
available. Clients owning resources should be closed when finished.

An `s3_object_storage` service additionally implements the marker
`AbstractS3ObjectStorageService`; it exposes an S3-compatible endpoint and
exports connection credentials via `get_secrets()`. The marker does not promise
support for every optional S3 operation. MinIO exports these fields under
`s3_connection` together with its certificate when available; its legacy
`minio_root_credentials` export is retained.
