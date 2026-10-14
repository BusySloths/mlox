# Operations demonstrator

This demonstrator runs one instrumented model pipeline:

```text
input.normalize -> pca.transform -> regression.predict -> quality.evaluate
```

The traffic generator sends reproducible, lightly noisy batches through MLflow
Gateway. `on` injects a deterministic PCA fault and `off` restores normal
behaviour. Operations infers the likely origin from step observations and
rolling quality statistics; the fault flag itself is not exported.

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

Open the MLOX TUI, select the project root, and open **Operations → Settings**.
Select the telemetry monitor bound to the gateway, then press **Start Watching**.
The selection remains fixed for that watch session. Return to **Incidents** and
start traffic in another terminal:

```sh
uv run -m examples.operations_demo.traffic
```

Noise is configurable when a different signal-to-noise ratio is useful:

```sh
uv run -m examples.operations_demo.traffic --feature-noise 0.03 --label-noise 0.02
```

Use prediction-only traffic when labels are delayed or unavailable:

```sh
uv run -m examples.operations_demo.traffic --without-labels
```

Prediction-only traffic requires the `champion` version with the optional-target
signature. Re-run registration to advance the alias; no gateway redeploy is
needed. Older versions require the `target` column, which the script detects.

The script selects the first running gateway. `status` shows its endpoint and
bound registry, telemetry, and secret manager. With multiple gateways:

```text
gateways
use <gateway-uuid>
```

You can also select one at startup (an unambiguous UUID prefix is accepted):

```sh
uv run -m examples.operations_demo.traffic --gateway <gateway-uuid>
```

Leave corruption off for the first ten runs of each observed workload. A new
model version needs a new watch and baseline. At the prompt:

```text
on      inject the PCA fault
off     restore normal PCA behavior
labels on/off  include or omit target labels (controls immediate RMSE telemetry)
status  show the current mode
gateways list configured gateways and mark the selected one
use ID  send subsequent requests through gateway ID
quit    stop traffic
```

Operations has five focused views:

- **Team** holds project-backed agent profiles, conversations, and proposals.
  The Pipeline Observer is advisory-only.
- **Pipelines** shows baselines, rolling quality or duration metrics, incidents,
  and frozen details. It can investigate and save a recovered incident as a
  Knowledge postmortem.
- **Plan** projects the Knowledge board titled `Operations`.
- **Activity** is the append-only Operations audit trail.
- **Settings** selects a telemetry monitor, controls watching, and stores an
  optional OpenAI-compatible reasoning provider in the active secret manager.

The incident view should first highlight `pca.transform`, show the downstream
regression/RMSE deviation, and report recovery after corrupted samples leave the
rolling windows.

This controlled scenario assumes immediate labels by default. Real deployments
may instead use delayed labels, business KPIs, canary tests, or model-quality
proxies; turn labels off in the traffic generator to exercise that case.
