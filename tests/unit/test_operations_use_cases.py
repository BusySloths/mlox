from __future__ import annotations

import json
from types import SimpleNamespace

from mlox.application.use_cases.operations import (
    OperationsWatchSession,
    list_operations_monitors,
    refresh_operations_watch,
    start_operations_watch,
)


def _attribute(key, value):
    if isinstance(value, int):
        encoded = {"intValue": str(value)}
    elif isinstance(value, float):
        encoded = {"doubleValue": value}
    else:
        encoded = {"stringValue": value}
    return {"key": key, "value": encoded}


def _span(trace, span, name, started, **attrs):
    return {
        "traceId": trace,
        "spanId": span,
        "name": name,
        "startTimeUnixNano": str(started),
        "endTimeUnixNano": str(started + 10),
        "attributes": [_attribute(key, value) for key, value in attrs.items()],
    }


def _run(
    number,
    *,
    pca=1.0,
    regression=2.0,
    rmse=0.1,
    model="demo",
    version="1",
    pipeline="operations-demo",
):
    trace = f"trace-{model}-{pipeline}-{number}"
    common = {
        "mlox.model.name": model,
        "mlox.model.version": version,
        "mlox.pipeline.name": pipeline,
    }
    spans = [
        _span(
            trace,
            f"root-{model}-{pipeline}-{number}",
            "mlox.model.live_predict",
            number * 100,
            **common,
        )
    ]
    values = [
        ("input.normalize", 0.0, "output.mean"),
        ("pca.transform", pca, "output.mean"),
        ("regression.predict", regression, "output.mean"),
        ("quality.evaluate", rmse, "rmse.mean"),
    ]
    for index, (name, value, observation) in enumerate(values, start=1):
        attrs = {
            **common,
            "mlox.step.path": f"{model}/pipeline/{name}",
            "mlox.step.name": name,
            "mlox.step.depth": 2,
            f"mlox.observation.{observation}": value,
        }
        spans.append(
            _span(
                trace,
                f"step-{model}-{pipeline}-{number}-{index}",
                "mlox.model.step",
                number * 100 + index,
                **attrs,
            )
        )
    return spans


def _raw(*runs):
    spans = [span for run in runs for span in run]
    return json.dumps({"resourceSpans": [{"scopeSpans": [{"spans": spans}]}]})


def test_watch_calibrates_detects_first_deviation_and_recovery():
    session = OperationsWatchSession(baseline_runs=2)
    session.start("")

    assert session.ingest(_raw(_run(1))) == 1
    assert session.snapshot()["state"] == "calibrating"

    session.ingest(_raw(_run(1), _run(2)))
    assert session.snapshot()["state"] == "watching"

    session.ingest(_raw(_run(1), _run(2), _run(3, pca=10, regression=20, rmse=5)))
    incident = session.snapshot()
    assert incident["state"] == "incident"
    assert incident["culprit"] == "demo/pipeline/pca.transform"
    assert incident["baseline_rmse"] == 0.1
    assert incident["latest_rmse"] == 5

    session.ingest(_raw(*(_run(number) for number in range(1, 14))))
    assert session.snapshot()["state"] == "recovered"
    session.stop()
    assert session.snapshot()["state"] == "recovered"
    assert not session.snapshot()["active"]


def test_start_uses_existing_telemetry_as_watermark():
    telemetry = _raw(_run(1))
    service = SimpleNamespace(get_telemetry_data=lambda bundle: telemetry)
    infra = SimpleNamespace(
        bundles=[SimpleNamespace(name="demo", services=[service])]
    )

    result = start_operations_watch(infra, baseline_runs=1)

    assert result.success
    session = result.data["session"]
    assert refresh_operations_watch(infra, session).data["snapshot"]["runs"] == 0


def test_start_requires_a_telemetry_source():
    result = start_operations_watch(SimpleNamespace(bundles=[]))

    assert not result.success
    assert "telemetry collector" in result.message


def test_watch_uses_selected_monitor_for_start_and_refresh():
    readings = {
        "wrong": [_raw(_run(1))],
        "right": ["", _raw(_run(2))],
    }

    def monitor(name, uuid):
        def read(_bundle):
            values = readings[name]
            return values.pop(0) if len(values) > 1 else values[0]

        return SimpleNamespace(
            name=name,
            uuid=uuid,
            state="running",
            get_telemetry_data=read,
        )

    wrong = monitor("wrong", "monitor-wrong")
    right = monitor("right", "monitor-right")
    infra = SimpleNamespace(
        bundles=[
            SimpleNamespace(
                name="first",
                server=SimpleNamespace(ip="10.0.0.1"),
                services=[wrong],
            ),
            SimpleNamespace(
                name="second",
                server=SimpleNamespace(ip="10.0.0.2"),
                services=[right],
            ),
        ]
    )

    monitors = list_operations_monitors(infra)
    result = start_operations_watch(
        infra, baseline_runs=1, monitor_uuid="monitor-right"
    )
    session = result.data["session"]
    refreshed = refresh_operations_watch(infra, session)

    assert [item["uuid"] for item in monitors] == ["monitor-wrong", "monitor-right"]
    assert monitors[1]["server"] == "10.0.0.2"
    assert result.success
    assert session.monitor_uuid == "monitor-right"
    assert session.monitor_name == "right"
    assert refreshed.data["snapshot"]["runs"] == 1


def test_start_rejects_missing_selected_monitor():
    result = start_operations_watch(
        SimpleNamespace(bundles=[]), monitor_uuid="missing-monitor"
    )

    assert not result.success
    assert "selected telemetry monitor" in result.message


def test_watch_calculates_bounded_rolling_averages():
    session = OperationsWatchSession(baseline_runs=2)
    session.start("")
    session.ingest(
        _raw(*(_run(number, pca=float(number)) for number in range(1, 13)))
    )

    pipeline = session.snapshot()["pipelines"][0]
    pca = next(step for step in pipeline["steps"] if step["name"] == "pca.transform")
    observation = next(
        item for item in pca["observations"] if item["name"] == "output.mean"
    )

    assert observation["current"] == 12.0
    assert observation["short_window"] == 10.0
    assert observation["long_window"] == 7.5


def test_watch_keeps_independent_pipeline_summaries():
    session = OperationsWatchSession(baseline_runs=1)
    session.start("")
    session.ingest(
        _raw(
            _run(1, model="forecast", version="2", pipeline="forecasting"),
            _run(1, model="ranking", version="7", pipeline="ranking"),
        )
    )

    snapshot = session.snapshot()
    pipelines = {item["pipeline_name"]: item for item in snapshot["pipelines"]}

    assert snapshot["runs"] == 2
    assert set(pipelines) == {"forecasting", "ranking"}
    assert pipelines["forecasting"]["model_name"] == "forecast"
    assert pipelines["ranking"]["model_version"] == "7"
    assert pipelines["forecasting"]["quality_name"] == "rmse.mean"
