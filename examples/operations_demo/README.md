# Operations demonstrator

This demonstrator runs one instrumented model pipeline:

```text
input.normalize -> pca.transform -> regression.predict -> quality.evaluate
```

The traffic generator sends a fixed labelled batch through the MLflow Gateway.
Its interactive `on` command injects a deterministic fault into the PCA output;
`off` restores normal behavior. The fault flag is not exported as diagnosis
evidence. Operations derives the likely origin from step observations and RMSE.

## Prerequisites

Use an existing MLOX project containing running MLflow, OpenTelemetry Collector,
and MLflow Gateway services. Bind the collector to the gateway so model spans are
exported, then set:

```sh
export MLOX_PROJECT_PATH="/path/to/project.mlox"
export MLOX_PROJECT_PASSWORD="your-project-password"
```

Register the model and assign its `champion` alias:

```sh
uv run -m examples.operations_demo.register
```

Open the MLOX TUI, select the project root, open **Operations**, and press
**Start Watching**. Then start traffic in another terminal:

```sh
uv run -m examples.operations_demo.traffic
```

Leave corruption off while the first ten runs establish the assumed-normal
baseline. At the interactive prompt use:

```text
on      inject the PCA fault
off     restore normal PCA behavior
status  show the current mode
quit    stop traffic
```

The Operations tab should first highlight `pca.transform`, show the downstream
regression/RMSE deviation, and report recovery after corruption is disabled.

This controlled scenario assumes immediate labels. Real deployments may instead
use delayed labels, business KPIs, canary tests, or model-quality proxies.
