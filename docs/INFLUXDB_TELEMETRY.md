# InfluxDB telemetry

MLOX deploys `influxdb:3.12.0-core` with persistent Docker storage, TLS, a health
check, token authentication, and a seven-day retention period for its telemetry
database. The deployment intentionally does not migrate,
back up, or run compatibility services for the retired Influx 1.x definition.

Service secrets are collected into the selected MLOX secret manager. Managed
runtimes receive `MLOX_INFLUX_URL`, `MLOX_INFLUX_TOKEN`,
`MLOX_INFLUX_DATABASE`, and (when TLS is used) `MLOX_INFLUX_CERTIFICATE_B64`.
Applications use `InfluxClient.from_env()`; it returns `None` without a binding.
External clients can call `InfluxClient.from_keyfile(service_name, keyfile, password)`
instead of embedding a token.

Collector destinations are all-signal: an enabled destination receives metrics,
logs, and traces. For Influx 3 Core, the Collector uses its `influxdb` exporter
against the `/api/v2/write` compatibility endpoint: `bucket` is the Core database
and the exporter-required `org` is `mlox` (Core ignores it). File output is
optional diagnostics only. Destination updates render and validate the pinned
Collector configuration, restart it, wait for health, and restore the previous
rendered destination settings when validation or health fails.

Operations uses the Influx query backend and has fixed limits: a 300-second query
window, 500 rows, and a 30-second request timeout. The service TUI shows bounded
recent metric, span, and log rows alongside health and measurements. Metric rows
are sampled from at most 12 metric measurements, with MLOX measurements shown
first. The TUI omits tokens, certificates, arbitrary SQL, and unbounded data
views.
