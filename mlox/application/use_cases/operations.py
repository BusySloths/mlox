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
    path: str
    name: str
    depth: int
    started_ns: int
    observations: dict[str, float]


@dataclass(frozen=True)
class PipelineRun:
    trace_id: str
    model_name: str
    model_version: str
    pipeline_name: str
    started_ns: int
    steps: tuple[PipelineStepRun, ...]


@dataclass
class OperationsWatchSession:
    """Bounded, in-memory baseline and incident analysis for one model pipeline."""

    baseline_runs: int = 10
    max_runs: int = 200
    active: bool = False
    state: str = "stopped"
    model_name: str = ""
    runs: list[PipelineRun] = field(default_factory=list)
    seen_span_ids: set[str] = field(default_factory=set)
    _pending: dict[str, dict[str, dict[str, Any]]] = field(
        default_factory=lambda: defaultdict(dict), repr=False
    )
    incident_seen: bool = False

    def start(self, raw: str | None) -> None:
        """Start after the current telemetry watermark; earlier data is ignored."""

        self.active = True
        self.state = "calibrating"
        self.model_name = ""
        self.runs.clear()
        self._pending.clear()
        self.incident_seen = False
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
            if not self.model_name or run.model_name == self.model_name:
                if not self.model_name:
                    self.model_name = run.model_name
                completed.append(run)

        completed.sort(key=lambda run: run.started_ns)
        self.runs.extend(completed)
        self.runs = self.runs[-self.max_runs:]
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
                    path=path,
                    name=str(attrs.get("mlox.step.name") or path.rsplit("/", 1)[-1]),
                    depth=int(attrs.get("mlox.step.depth") or 1),
                    started_ns=int(span.get("startTimeUnixNano") or 0),
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
            model_name=str(attrs.get("mlox.model.name") or "unknown"),
            model_version=str(attrs.get("mlox.model.version") or "unknown"),
            pipeline_name=str(attrs.get("mlox.pipeline.name") or "model pipeline"),
            started_ns=int(root.get("startTimeUnixNano") or 0),
            steps=tuple(steps),
        )

    def _baseline(self) -> dict[tuple[str, str], list[float]]:
        baseline: dict[tuple[str, str], list[float]] = defaultdict(list)
        for run in self.runs[:self.baseline_runs]:
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

    def _step_rows(self) -> list[dict[str, Any]]:
        if not self.runs:
            return []
        baseline = self._baseline()
        latest = self.runs[-1]
        rows: list[dict[str, Any]] = []
        for step in latest.steps:
            comparisons = []
            for name, value in step.observations.items():
                reference = baseline.get((step.path, name), [])
                if reference:
                    comparisons.append(
                        {
                            "name": name,
                            "baseline": statistics.median(reference),
                            "current": value,
                            "anomalous": self._is_anomalous(value, reference),
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

    def _update_state(self) -> None:
        if len(self.runs) < self.baseline_runs:
            self.state = "calibrating"
            return
        anomalous = any(row["state"] == "anomalous" for row in self._step_rows())
        if anomalous:
            self.incident_seen = True
            self.state = "incident"
        elif self.incident_seen:
            self.state = "recovered"
        else:
            self.state = "watching"

    def snapshot(self) -> dict[str, Any]:
        rows = self._step_rows() if len(self.runs) >= self.baseline_runs else []
        culprit = next(
            (
                row["path"]
                for row in rows
                if row["state"] == "anomalous"
                and row["name"] != "quality.evaluate"
            ),
            "",
        )
        latest_rmse = None
        baseline_rmse = None
        for row in rows:
            for observation in row["observations"]:
                if observation["name"] in {"rmse.value", "rmse.mean"}:
                    latest_rmse = observation["current"]
                    baseline_rmse = observation["baseline"]
        return {
            "active": self.active,
            "state": self.state,
            "model_name": self.model_name,
            "runs": len(self.runs),
            "baseline_runs": min(len(self.runs), self.baseline_runs),
            "baseline_target": self.baseline_runs,
            "steps": rows,
            "culprit": culprit,
            "latest_rmse": latest_rmse,
            "baseline_rmse": baseline_rmse,
        }


def _telemetry_source(infra) -> tuple[Any, Any] | tuple[None, None]:
    for bundle in getattr(infra, "bundles", []) or []:
        for service in getattr(bundle, "services", []) or []:
            if callable(getattr(service, "get_telemetry_data", None)):
                return bundle, service
    return None, None


def start_operations_watch(infra, *, baseline_runs: int = 10) -> OperationResult:
    bundle, service = _telemetry_source(infra)
    if bundle is None or service is None:
        return OperationResult(False, 30, "No telemetry collector is available.")
    try:
        raw = service.get_telemetry_data(bundle)
    except Exception as exc:
        return OperationResult(False, 31, f"Could not read telemetry: {exc}")
    session = OperationsWatchSession(baseline_runs=baseline_runs)
    session.start(raw)
    return OperationResult(
        True,
        0,
        "Operations watch started; existing telemetry was ignored.",
        {"session": session, "snapshot": session.snapshot()},
    )


def refresh_operations_watch(infra, session: OperationsWatchSession) -> OperationResult:
    bundle, service = _telemetry_source(infra)
    if bundle is None or service is None:
        return OperationResult(False, 30, "No telemetry collector is available.")
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
