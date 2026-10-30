# MLflow tracking and model registry

MLOX supports MLflow 3.8.1 for tracking experiments, storing artifacts, and
registering models. Add the `mlflow-3.8.1-docker` service to a Docker server in
MLOX. Setup creates credentials and exposes the MLflow UI and API over HTTPS
through Traefik. Use the URL and credentials shown by the service to connect
an MLflow client.

The complete list of deployment variants lives in the generated
[service catalog](../../../docs/SERVICES_CATALOG.md).

## Implementation

- `mlox.mlflow.3.8.1.yaml` is the service descriptor.
- `docker-compose-mlflow-3.8.1.yaml` defines the tracking server and HTTPS proxy.
- `docker.py` provides the `MLFlowDockerService` deployment adapter.
- `docker_mlflow3.py` retains the old 3.x class import as a compatibility alias
  for saved workspace state; it does not provide a separate implementation.

MLflow 2.22 tracking and MLServer templates have been removed. This removal
does not upgrade existing deployments or migrate their databases. Existing
2.22 deployments require a separate migration before using the supported
3.8.1 templates.

## Model serving

After creating a registry, choose a serving service and bind it to that registry:

- [MLflow Gateway](../mlflow_gateway/README.md) loads and caches models on demand.
- [MLServer](../mlflow_mlserver/README.md) serves one registered model per deployment.

## Integration tests and diagnostics

The tracking tests and shared registry fixture are in
[`tests/integration/test_service_mlflow.py`](../../../tests/integration/test_service_mlflow.py).
Gateway, MLServer, and telemetry integration tests use that same fixture.
Run the focused tracking tests on a Multipass-capable host:

```bash
task tests:integration:service SERVICE=mlflow -- --integration-log-dir .tmp/mlox-logs --integration-quiet
```

The terminal shows each test and its result. A unique run directory contains
module logs with setup, test, and teardown output. Readiness checks wait for
Compose containers and then query the MLflow registry API. A failed API probe
includes the client exception with the configured password redacted; failed
readiness also collects Compose state and container logs. Use those details to
distinguish container startup failures from connection or authentication errors.
