"""Observe model pipelines and compare live telemetry with a normal baseline."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
import json
import math
import statistics
from typing import Any

from mlox.application.result import OperationResult


OBSERVATION_PREFIX = "mlox.observation."


def _attributes(attributes: Any) -> dict[str, Any]:
    values: dict[str, Any] = {}
    for item in attributes or []:
        if not isinstance(item, dict) or not item.get("key"):
            continue
        encoded = item.get("value") or {}
        value = next(iter(encoded.values()), None) if isinstance(encoded, dict) else None
        values[str(item["key"])] = value
    return values


def _spans(raw: str | None) -> list[dict[str, Any]]:
    spans: list[dict[str, Any]] = []
    for line in (raw or "").splitlines():
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        for resource in payload.get("resourceSpans", []):
            for scope in resource.get("scopeSpans", []):
                spans.extend(scope.get("spans", []))
    return spans


def _numeric_observations(attributes: dict[str, Any]) -> dict[str, float]:
    observations: dict[str, float] = {}
    for key, value in attributes.items():
        if not key.startswith(OBSERVATION_PREFIX):
            continue
        if key.endswith((".dimensions", ".size")):
            continue
        try:
            observations[key.removeprefix(OBSERVATION_PREFIX)] = float(value)
        except (TypeError, ValueError):
            continue
    return observations


@dataclass(frozen=True)
class PipelineStepRun:
    span_id: str
    path: str
    name: str
    depth: int
    started_ns: int
    labels: dict[str, Any]
    observations: dict[str, float]


@dataclass(frozen=True)
class PipelineRun:
    trace_id: str
    span_id: str
    pipeline_id: str
    model_name: str
    model_version: str
    model_alias: str
    pipeline_name: str
    request_id: str
    started_ns: int
    labels: dict[str, Any]
    steps: tuple[PipelineStepRun, ...]


@dataclass
class OperationsWatchSession:
    """Bounded, in-memory baseline and incident analysis for model pipelines."""

    baseline_runs: int = 10
    max_runs: int = 200
    active: bool = False
    state: str = "stopped"
    model_name: str = ""
    monitor_uuid: str = ""
    monitor_name: str = ""
    runs: list[PipelineRun] = field(default_factory=list)
    seen_span_ids: set[str] = field(default_factory=set)
    _pending: dict[str, dict[str, dict[str, Any]]] = field(
        default_factory=lambda: defaultdict(dict), repr=False
    )
    incident_pipelines: set[tuple[str, str, str]] = field(default_factory=set)

    def start(self, raw: str | None) -> None:
        """Start after the current telemetry watermark; earlier data is ignored."""

        self.active = True
        self.state = "calibrating"
        self.model_name = ""
        self.runs.clear()
        self._pending.clear()
        self.incident_pipelines.clear()
        self.seen_span_ids = {
            str(span.get("spanId")) for span in _spans(raw) if span.get("spanId")
        }

    def stop(self) -> None:
        self.active = False

    def ingest(self, raw: str | None) -> int:
        if not self.active:
            return 0
        for span in _spans(raw):
            span_id = str(span.get("spanId") or "")
            trace_id = str(span.get("traceId") or "")
            if not span_id or not trace_id or span_id in self.seen_span_ids:
                continue
            self.seen_span_ids.add(span_id)
            self._pending[trace_id][span_id] = span

        completed: list[PipelineRun] = []
        for trace_id, spans_by_id in list(self._pending.items()):
            spans = list(spans_by_id.values())
            if not any(span.get("name") == "mlox.model.live_predict" for span in spans):
                continue
            run = self._pipeline_run(trace_id, spans)
            if run is None:
                continue
            del self._pending[trace_id]
            completed.append(run)

        completed.sort(key=lambda run: run.started_ns)
        self.runs.extend(completed)
        grouped = self._grouped_runs()
        self.runs = sorted(
            (run for runs in grouped.values() for run in runs[-self.max_runs:]),
            key=lambda run: run.started_ns,
        )
        if self.runs:
            self.model_name = self.runs[-1].model_name
        self._update_state()
        return len(completed)

    def _pipeline_run(
        self, trace_id: str, spans: list[dict[str, Any]]
    ) -> PipelineRun | None:
        roots = [span for span in spans if span.get("name") == "mlox.model.live_predict"]
        steps: list[PipelineStepRun] = []
        for span in spans:
            if span.get("name") != "mlox.model.step":
                continue
            attrs = _attributes(span.get("attributes"))
            path = str(attrs.get("mlox.step.path") or "")
            if not path:
                continue
            steps.append(
                PipelineStepRun(
                    span_id=str(span.get("spanId") or ""),
                    path=path,
                    name=str(attrs.get("mlox.step.name") or path.rsplit("/", 1)[-1]),
                    depth=int(attrs.get("mlox.step.depth") or 1),
                    started_ns=int(span.get("startTimeUnixNano") or 0),
                    labels={
                        key: value
                        for key, value in attrs.items()
                        if not key.startswith(OBSERVATION_PREFIX)
                    },
                    observations=_numeric_observations(attrs),
                )
            )
        if not roots or not steps:
            return None
        root = min(roots, key=lambda span: int(span.get("startTimeUnixNano") or 0))
        attrs = _attributes(root.get("attributes"))
        steps.sort(key=lambda step: step.started_ns)
        return PipelineRun(
            trace_id=trace_id,
            span_id=str(root.get("spanId") or ""),
            pipeline_id=str(attrs.get("mlox.pipeline.id") or ""),
            model_name=str(attrs.get("mlox.model.name") or "unknown"),
            model_version=str(attrs.get("mlox.model.version") or "unknown"),
            model_alias=str(attrs.get("mlox.model.alias") or ""),
            pipeline_name=str(attrs.get("mlox.pipeline.name") or "model pipeline"),
            request_id=str(attrs.get("mlox.request.id") or ""),
            started_ns=int(root.get("startTimeUnixNano") or 0),
            labels=attrs,
            steps=tuple(steps),
        )

    @staticmethod
    def _key(run: PipelineRun) -> tuple[str, str, str]:
        return run.model_name, run.model_version, run.pipeline_name

    def _grouped_runs(self) -> dict[tuple[str, str, str], list[PipelineRun]]:
        grouped: dict[tuple[str, str, str], list[PipelineRun]] = defaultdict(list)
        for run in self.runs:
            grouped[self._key(run)].append(run)
        return grouped

    def _baseline(
        self, runs: list[PipelineRun]
    ) -> dict[tuple[str, str], list[float]]:
        baseline: dict[tuple[str, str], list[float]] = defaultdict(list)
        for run in runs[: self.baseline_runs]:
            for step in run.steps:
                for name, value in step.observations.items():
                    if math.isfinite(value):
                        baseline[(step.path, name)].append(value)
        return baseline

    @staticmethod
    def _is_anomalous(value: float, baseline: list[float]) -> bool:
        if not baseline or not math.isfinite(value):
            return False
        center = statistics.median(baseline)
        deviations = [abs(point - center) for point in baseline]
        mad = statistics.median(deviations)
        spread = statistics.pstdev(baseline) if len(baseline) > 1 else 0.0
        tolerance = max(6.0 * mad, 4.0 * spread, abs(center) * 0.25, 1e-6)
        return abs(value - center) > tolerance

    @staticmethod
    def _window_average(
        runs: list[PipelineRun],
        step_path: str,
        observation_name: str,
        *,
        duration_ns: int,
        max_samples: int,
    ) -> float | None:
        if not runs:
            return None
        cutoff = runs[-1].started_ns - duration_ns
        values: list[float] = []
        for run in reversed(runs):
            if run.started_ns < cutoff:
                break
            for step in run.steps:
                if step.path == step_path and observation_name in step.observations:
                    value = step.observations[observation_name]
                    if math.isfinite(value):
                        values.append(value)
                    break
            if len(values) >= max_samples:
                break
        return statistics.mean(values) if values else None

    def _step_rows(self, runs: list[PipelineRun]) -> list[dict[str, Any]]:
        if not runs:
            return []
        baseline = self._baseline(runs)
        latest = runs[-1]
        rows: list[dict[str, Any]] = []
        for step in latest.steps:
            comparisons = []
            for name, value in step.observations.items():
                reference = baseline.get((step.path, name), [])
                if reference:
                    short_window = self._window_average(
                        runs,
                        step.path,
                        name,
                        duration_ns=60 * 1_000_000_000,
                        max_samples=5,
                    )
                    long_window = self._window_average(
                        runs,
                        step.path,
                        name,
                        duration_ns=5 * 60 * 1_000_000_000,
                        max_samples=10,
                    )
                    comparisons.append(
                        {
                            "name": name,
                            "baseline": statistics.median(reference),
                            "current": value,
                            "short_window": short_window,
                            "long_window": long_window,
                            "anomalous": any(
                                candidate is not None
                                and self._is_anomalous(candidate, reference)
                                for candidate in (short_window, long_window)
                            ),
                        }
                    )
            anomalous = any(item["anomalous"] for item in comparisons)
            rows.append(
                {
                    "path": step.path,
                    "name": step.name,
                    "depth": step.depth,
                    "state": "anomalous" if anomalous else "normal",
                    "observations": comparisons,
                }
            )
        return rows

    def _pipeline_state(
        self, key: tuple[str, str, str], runs: list[PipelineRun]
    ) -> str:
        if len(runs) < self.baseline_runs:
            return "calibrating"
        anomalous = any(
            row["state"] == "anomalous" for row in self._step_rows(runs)
        )
        if anomalous:
            self.incident_pipelines.add(key)
            return "incident"
        if key in self.incident_pipelines:
            return "recovered"
        return "watching"

    def _update_state(self) -> None:
        states = [
            self._pipeline_state(key, runs)
            for key, runs in self._grouped_runs().items()
        ]
        if not states:
            self.state = "calibrating"
        elif "incident" in states:
            self.state = "incident"
        elif "calibrating" in states:
            self.state = "calibrating"
        elif "recovered" in states:
            self.state = "recovered"
        else:
            self.state = "watching"

    @staticmethod
    def _quality_metric(rows: list[dict[str, Any]]) -> dict[str, Any] | None:
        preferred = ("rmse", "mae", "mse", "error", "accuracy", "f1", "precision", "recall")
        observations = [
            observation
            for row in rows
            if row.get("name") == "quality.evaluate"
            for observation in row.get("observations", [])
        ]
        if not observations:
            observations = [
                observation
                for row in rows
                for observation in row.get("observations", [])
            ]
        return next(
            (
                observation
                for metric in preferred
                for observation in observations
                if str(observation.get("name", "")).lower().startswith(metric)
            ),
            None,
        )

    def _pipeline_snapshot(
        self, key: tuple[str, str, str], runs: list[PipelineRun]
    ) -> dict[str, Any]:
        state = self._pipeline_state(key, runs)
        rows = self._step_rows(runs)
        culprit = next(
            (
                row["path"]
                for row in rows
                if row["state"] == "anomalous"
                and row["name"] != "quality.evaluate"
            ),
            "",
        )
        quality = self._quality_metric(rows)
        model_name, model_version, pipeline_name = key
        latest = runs[-1]
        return {
            "id": "\x1f".join(key),
            "pipeline_name": pipeline_name,
            "model_name": model_name,
            "model_version": model_version,
            "state": state,
            "runs": len(runs),
            "baseline_runs": min(len(runs), self.baseline_runs),
            "baseline_target": self.baseline_runs,
            "steps": rows,
            "culprit": culprit,
            "quality_name": quality.get("name") if quality else "",
            "quality_value": quality.get("long_window") if quality else None,
            "quality_current": quality.get("current") if quality else None,
            "quality_baseline": quality.get("baseline") if quality else None,
            "details": {
                "trace_id": latest.trace_id,
                "span_id": latest.span_id,
                "pipeline_id": latest.pipeline_id,
                "pipeline_name": latest.pipeline_name,
                "request_id": latest.request_id,
                "model_name": latest.model_name,
                "model_version": latest.model_version,
                "model_alias": latest.model_alias,
                "started_ns": latest.started_ns,
                "labels": latest.labels,
                "steps": [
                    {
                        "span_id": step.span_id,
                        "path": step.path,
                        "name": step.name,
                        "depth": step.depth,
                        "started_ns": step.started_ns,
                        "labels": step.labels,
                        "observations": step.observations,
                    }
                    for step in latest.steps
                ],
            },
        }

    def snapshot(self) -> dict[str, Any]:
        pipelines = [
            self._pipeline_snapshot(key, runs)
            for key, runs in self._grouped_runs().items()
        ]
        pipelines.sort(key=lambda item: (item["pipeline_name"], item["model_name"]))
        primary = pipelines[0] if pipelines else {}
        return {
            "active": self.active,
            "state": self.state,
            "model_name": primary.get("model_name", self.model_name),
            "runs": len(self.runs),
            "baseline_runs": primary.get("baseline_runs", 0),
            "baseline_target": self.baseline_runs,
            "steps": primary.get("steps", []),
            "culprit": primary.get("culprit", ""),
            "latest_rmse": primary.get("quality_current"),
            "baseline_rmse": primary.get("quality_baseline"),
            "pipelines": pipelines,
        }


def list_operations_monitors(infra) -> list[dict[str, str]]:
    """Return services that can provide raw telemetry for operations analysis."""

    monitors: list[dict[str, str]] = []
    for bundle in getattr(infra, "bundles", []) or []:
        for service in getattr(bundle, "services", []) or []:
            if callable(getattr(service, "get_telemetry_data", None)):
                monitors.append(
                    {
                        "uuid": str(getattr(service, "uuid", "")),
                        "name": str(getattr(service, "name", "Telemetry monitor")),
                        "state": str(getattr(service, "state", "unknown")),
                        "bundle": str(getattr(bundle, "name", "-")),
                        "server": str(
                            getattr(getattr(bundle, "server", None), "ip", "-")
                        ),
                    }
                )
    return monitors


def _telemetry_source(
    infra, monitor_uuid: str | None = None
) -> tuple[Any, Any] | tuple[None, None]:
    for bundle in getattr(infra, "bundles", []) or []:
        for service in getattr(bundle, "services", []) or []:
            if not callable(getattr(service, "get_telemetry_data", None)):
                continue
            if monitor_uuid and str(getattr(service, "uuid", "")) != monitor_uuid:
                continue
            return bundle, service
    return None, None


def start_operations_watch(
    infra,
    *,
    baseline_runs: int = 10,
    monitor_uuid: str | None = None,
) -> OperationResult:
    bundle, service = _telemetry_source(infra, monitor_uuid)
    if bundle is None or service is None:
        message = (
            "The selected telemetry monitor is no longer available."
            if monitor_uuid
            else "No telemetry collector is available."
        )
        return OperationResult(False, 30, message)
    try:
        raw = service.get_telemetry_data(bundle)
    except Exception as exc:
        return OperationResult(False, 31, f"Could not read telemetry: {exc}")
    session = OperationsWatchSession(baseline_runs=baseline_runs)
    session.monitor_uuid = str(getattr(service, "uuid", ""))
    session.monitor_name = str(getattr(service, "name", "Telemetry monitor"))
    session.start(raw)
    return OperationResult(
        True,
        0,
        "Operations watch started; existing telemetry was ignored.",
        {"session": session, "snapshot": session.snapshot()},
    )


def refresh_operations_watch(infra, session: OperationsWatchSession) -> OperationResult:
    bundle, service = _telemetry_source(infra, session.monitor_uuid or None)
    if bundle is None or service is None:
        return OperationResult(
            False, 30, "The selected telemetry monitor is no longer available."
        )
    try:
        raw = service.get_telemetry_data(bundle)
        ingested = session.ingest(raw)
    except Exception as exc:
        return OperationResult(False, 31, f"Could not read telemetry: {exc}")
    return OperationResult(
        True,
        0,
        f"Operations watch ingested {ingested} new run(s).",
        {"snapshot": session.snapshot()},
    )
