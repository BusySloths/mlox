# Repository Docker Deploy

Repository deployments are listed as applications and expose a health check based
on Docker Compose container state and any configured container health checks.
This does not independently probe the application's endpoints.

Secret-manager and telemetry providers can be bound independently. Mlox passes
the providers' environment variables to **every service in the Compose stack**
using per-deployment override files. The application must support those variables
and, for telemetry, must be instrumented to export signals. Changing a binding
recreates running Compose containers; stopped deployments pick up changes when
started. Variables supplied by a binding take precedence over matching variables
in the original Compose file.

The overrides are named `.mlox-<service-uuid>-secret-manager.yaml` and
`.mlox-<service-uuid>-telemetry.yaml` in the repository checkout. They are created
with owner-only permissions and may contain credentials. Do not commit or share
them. Mlox removes an override when its provider is unbound, and removes both
when the deployment is torn down. Existing deployments can be bound without
rerunning setup.
