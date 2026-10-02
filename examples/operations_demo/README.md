# Operations demonstrator

This demonstrator runs one instrumented model pipeline:

```text
input.normalize -> pca.transform -> regression.predict -> quality.evaluate
```

The traffic generator sends reproducible labelled batches with small feature and
label noise through the MLflow Gateway. Its interactive `on` command injects a
deterministic fault into the PCA output; `off` restores normal behavior. The
fault flag is not exported as diagnosis evidence. Operations derives the likely
origin from step observations and rolling model-quality statistics.

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

Open the MLOX TUI, select the project root, and open **Operations**. Select the
telemetry monitor bound to the gateway from the dropdown, then press **Start
Watching**. The selection remains fixed for that watch session. Start traffic
in another terminal:

```sh
uv run -m examples.operations_demo.traffic
```

Noise is configurable when a different signal-to-noise ratio is useful:

```sh
uv run -m examples.operations_demo.traffic --feature-noise 0.03 --label-noise 0.02
```

The script selects the first running MLflow Gateway by default. Use `status` to
see the exact gateway endpoint and its bound registry, telemetry, and secret
manager services. If the project contains multiple gateways, list and select
them interactively:

```text
gateways
use <gateway-uuid>
```

You can also select one at startup (an unambiguous UUID prefix is accepted):

```sh
uv run -m examples.operations_demo.traffic --gateway <gateway-uuid>
```

Leave corruption off while the first ten runs for each observed pipeline
establish its assumed-normal baseline. At the interactive prompt use:

```text
on      inject the PCA fault
off     restore normal PCA behavior
status  show the current mode
gateways list configured gateways and mark the selected one
use ID  send subsequent requests through gateway ID
quit    stop traffic
```

The Operations tab summarizes every observed model pipeline and provides
baseline, current, 1-minute/5-sample, and 5-minute/10-sample values for the
selected pipeline. It should first highlight `pca.transform`, show the downstream
regression/RMSE deviation, and report recovery after corrupted samples leave the
rolling windows.

This controlled scenario assumes immediate labels. Real deployments may instead
use delayed labels, business KPIs, canary tests, or model-quality proxies.
