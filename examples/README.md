# Tracking and telemetry examples

From the repository root, with MLOX and its dependencies installed:

```sh
python -m examples.tracking.mlflow_tracking_example
python -m examples.otel.otel_client_example
```

No infrastructure is required. Tracking defaults to `mlox-example-mlflow.db`
(SQLite) in the current directory and local MLflow artifacts. The OTel example
reports missing telemetry and skips emission. The tracking example trains and
reloads a model with nested normalization, PCA and regression spans.

Existing MLflow (`MLFLOW_URI` or `MLFLOW_TRACKING_URI`), OTLP, and MLOX secret
manager environment settings take precedence. Alternatively set both
`MLOX_PROJECT_PATH` and `MLOX_PROJECT_PASSWORD`: running providers are discovered
by capability and export their standard environment bindings. Secret manager
and telemetry discovery are independent. No services are rebound or restarted.

When multiple providers exist, the first running entry in project order is used.
The selected service name, UUID and server are logged, including for MLflow.
To override discovery, select a name or UUID with
`MLOX_EXAMPLE_TELEMETRY`, `MLOX_EXAMPLE_SECRET_MANAGER`, or
`MLOX_EXAMPLE_TRACKER`. These selectors apply to project discovery; existing
environment bindings take precedence. Set either optional provider selector to
`none` to disable it, including an existing environment binding, for this process.

For example, exercise all four combinations by running the tracking command
with neither selector disabled, telemetry set to `none`, secret manager set to
`none`, and both set to `none`. Logs report found providers by name/UUID or
environment source, absent/disabled providers, and available model clients.
Credentials and secret contents are never printed. Client construction proves
configuration can be loaded, not server reachability; check collector data for
delivery. Invalid configuration fails visibly instead of silently disabling it.

For the forecasting variant, install
`examples/tracking/requirements_sktime_mlflow.txt` and run
`python -m examples.tracking.sktime_tracking_example`.
