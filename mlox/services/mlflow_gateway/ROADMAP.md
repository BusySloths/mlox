# MLflow Gateway Roadmap

This document collects ideas for evolving the MLflow Gateway into a more
professional, observable, reliable, and generally useful model-serving service.

The gateway already provides a useful foundation:

- Loading models from an MLflow model registry.
- An in-process model cache with TTL and LRU-style size limits.
- Model cache inspection and clearing endpoints.
- Basic per-cache-entry call timestamps and counters.
- Health reporting and authenticated HTTPS access through Traefik.

There are two distinct kinds of caching discussed below:

- **Model caching** avoids loading the same MLflow model repeatedly. This
  already exists.
- **Prediction caching** avoids running inference again for the same model,
  input, and parameters. This would be a new feature.

## 1. Production-grade metrics

Metrics should be maintained independently of model cache entries. Otherwise,
historical metrics disappear when a model is evicted or the cache is cleared.

Useful metrics include:

- Request count by model, resolved version, route, and status.
- Successful and failed predictions.
- Active, queued, and rejected requests.
- Request and inference duration, including p50, p90, p95, p99, and maximum.
- Model-load duration and model-load failures.
- Model-cache hits, misses, evictions, hit ratio, and current size.
- Prediction-cache hits, misses, evictions, hit ratio, and current size.
- Input and output sizes.
- First and last request timestamps.
- Requests per second/minute and peak throughput.
- Process CPU, memory, open file descriptors, and event-loop lag.

Expose machine-readable metrics through a standard Prometheus `/metrics`
endpoint and optionally export them through OpenTelemetry. High-cardinality
values such as request IDs, user IDs, and raw error messages must not be used as
metric labels; they belong in logs and traces.

## 2. Prediction-result caching

A prediction cache key should be calculated from a canonical representation of:

- Resolved model name and immutable model version.
- Input data.
- Prediction parameters.
- Optional preprocessing or schema version.

The resolved version must be part of the key rather than only an alias, because
an alias such as `prod` can be reassigned.

Prediction caching should provide:

- Configurable TTL.
- Maximum entries and maximum memory/byte size.
- LRU eviction.
- Per-model opt-in or opt-out.
- Explicit invalidation.
- An authorized cache-control request option.
- Maximum cacheable input and output sizes.
- A `prediction_cache_hit` field in the response.
- Single-flight protection against a cache stampede, so concurrent identical
  misses do not all calculate the same result.

Caching should be disabled by default for nondeterministic models and models
whose results depend on time or external state. Sensitive inputs may also make
a shared result cache inappropriate. An in-memory backend is sufficient for a
first implementation; Redis or a similar shared backend can later support
multiple gateway replicas.

## 3. Operational and administrative endpoints

Separate health, metrics, and administration responsibilities:

- `/livez`: report whether the process is alive without calling MLflow.
- `/readyz`: report whether the gateway is ready to accept predictions.
- `/metrics`: expose Prometheus-compatible metrics.
- `/admin/status`: show human-readable runtime and dependency state.
- `/admin/cache/models`: inspect, preload, invalidate, or clear loaded models.
- `/admin/cache/predictions`: inspect statistics and invalidate prediction
  results.
- `/admin/config`: show and update an allowlist of runtime settings.
- `/admin/drain`: stop accepting new work while active requests finish.

Runtime changes should be validated and audited. Safe mutable settings might
include cache limits, TTLs, log level, and experiment traffic weights.
Credentials, tracking URIs, and other security-sensitive configuration should
normally require a restart.

Administrative endpoints require stronger authorization than prediction
endpoints. A shared Basic Auth identity is too coarse once runtime mutation is
available.

## 4. Performance and load testing

Load generation should normally be an external test command or tool, while the
gateway exposes the measurements needed to evaluate the result. Candidates
include k6, Locust, or a small repository-owned benchmark client.

Benchmark at least these scenarios:

- Warm model with unique inputs.
- Warm model with repeated inputs.
- Cold model load.
- Multiple models competing for cache and memory.

Reports should contain:

- Sustainable requests per second.
- Latency percentiles.
- Error and timeout rate.
- CPU and memory usage at saturation.
- Maximum useful concurrency.
- Model-cache and prediction-cache hit rates.

An optional benchmark mode may disable verbose access logs, tag benchmark
traffic, or select a deterministic test model. It must not bypass normal
authentication, validation, or inference behavior.

## 5. A/B tests, canaries, and experiments

Every request should have the following correlation information:

- `request_id`: unique for each HTTP request.
- `trace_id`: correlates gateway and downstream telemetry.
- `experiment_id`: identifies an active experiment.
- `variant`: records the selected control or candidate route.
- `resolved_model_version`: records the model that was actually invoked.

Routing capabilities should include:

- Weighted routing, for example 90% to version 12 and 10% to version 13.
- Deterministic assignment based on a stable subject key.
- Random assignment when no stable subject key is available.
- Sticky assignment so a subject consistently receives the same variant.
- An authorized explicit override for testing.
- Experiment start/end time and lifecycle status.
- Fallback or circuit breaking for an unhealthy candidate.
- Exposure logging so outcomes can be joined to the variant actually served.

The gateway should not calculate domain-specific experiment success metrics.
Instead, it should emit reliable exposure records containing correlation data,
experiment, variant, resolved model version, and timestamp.

## 6. Reliability and traffic management

Important production controls include:

- Request and model-load timeouts.
- Maximum request body, input, and batch sizes.
- Bounded concurrency and queue length.
- Rate limits and per-client quotas.
- Graceful shutdown and request draining.
- Retries for safe registry operations only, not arbitrary predictions.
- A circuit breaker around the MLflow registry.
- Model preloading and cache warming.
- Background alias refresh.
- An optional fallback model or version.
- Admission control before memory is exhausted.
- Multiple workers or replicas with clearly defined shared-state behavior.

The current implementation temporarily mutates the process-global `sys.path`
while serving a model. Concurrent predictions using different dependencies can
therefore interfere with one another. Safe multi-user concurrency will require
dependency isolation, preferably separate worker processes or model runtimes,
rather than shared global import state.

## 7. API quality and compatibility

The public API should add:

- Versioned routes such as `/v1/predict`.
- A stable response envelope.
- Machine-readable error codes in addition to error messages.
- Request IDs in both a response header and response body.
- Consistent serialization for arrays, tables, scalars, and nested output.
- Input validation based on the MLflow model signature.
- Batch limits and documented partial-failure behavior.
- Idempotency-key support where appropriate.
- OpenAPI examples and client examples.
- A deprecation policy and backward-compatibility tests.

Raw prediction inputs and outputs should not be logged by default. They can
contain sensitive data and can make logs unmanageably large.

## 8. Security and governance

A production gateway should support:

- API keys, JWT/OIDC, or mutual TLS in addition to Basic Auth.
- Separate prediction, read-only operations, and administrator roles.
- Per-model authorization.
- Audit logs for configuration changes, cache clearing, and routing overrides.
- Secret rotation.
- Trusted TLS certificates and MLflow TLS verification.
- Configurable CORS rather than allowing every origin.
- Input size and complexity limits.
- Model and dependency provenance information.
- An optional model allowlist.
- A retention policy for request metadata.

## 9. Model lifecycle management

Useful lifecycle features include:

- Preloading selected production models at startup.
- Asynchronous loading with a visible loading state.
- Pinning important models so LRU does not evict them.
- Reporting estimated per-model memory consumption.
- Reloading or invalidating a model when an alias moves.
- Validating a model with a smoke-test input before serving it.
- Gradual rollout with automatic rollback.
- Tracking model-load errors separately from prediction errors.
- Exposing model build, runtime, and environment metadata.

## Suggested implementation order

1. Correct and separate request metrics from model-cache metadata.
2. Add request IDs, structured logs, latency/error metrics, and `/metrics`.
3. Fix concurrency safety and introduce limits, timeouts, and readiness.
4. Harden logging, CORS, TLS, and administrative authorization.
5. Add prediction caching behind explicit opt-in configuration.
6. Add model warming, invalidation, and lifecycle management.
7. Add experiment configuration and deterministic weighted routing.
8. Add shared cache/state and horizontal scaling when multiple replicas are
   required.

Observability, concurrency safety, operational limits, and security form the
professionalization baseline. Prediction caching and A/B routing are valuable
features, but are safer to build once that baseline is established.
