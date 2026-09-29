# Tracking and telemetry examples

Use an existing MLOX project with its dependencies installed. From the repository root:

```sh
export MLOX_PROJECT_PATH="/path/to/project.mlox"
export MLOX_PROJECT_PASSWORD="your-project-password"

uv run -m examples.tracking.mlflow_tracking_example
uv run -m examples.otel.otel_client_example
```

The examples select the first running provider of each kind and print its service
name, UUID and server. Telemetry and secret manager are independently optional;
missing providers are reported. Tracking requires a running MLflow service.

The tracking example saves and reloads a normalization → PCA → regression model
with nested telemetry steps. The OTel example emits spans, metrics and logs when
a collector is available. Check the collector to confirm delivery.

For the forecasting variant, install `examples/tracking/requirements_sktime_mlflow.txt`
and run `uv run -m examples.tracking.sktime_tracking_example`.
