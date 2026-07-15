from __future__ import annotations

import asyncio
import threading
from types import SimpleNamespace

from textual.app import App, ComposeResult
from textual.widgets import DataTable, Static

from mlox.application.use_cases import mlflow_gateway
from mlox.tui.services.mlflow_gateway import (
    MLflowGatewaySettingsPanel,
    settings,
)
from mlox.tui.services import mlflow_gateway as gateway_tui


METRICS = """# HELP mlox_gateway_predictions_total Predictions
mlox_gateway_http_requests_total{method="GET",route="/health",status="200"} 12
mlox_gateway_predictions_total{model="Demo",version="1",status="success"} 7
mlox_gateway_predictions_total{model="Demo",version="1",status="error"} 2
mlox_gateway_model_cache_operations_total{result="hit"} 7
mlox_gateway_model_cache_operations_total{result="miss"} 2
mlox_gateway_http_request_duration_seconds_bucket{method="GET",le="1.0"} 12
mlox_gateway_http_request_duration_seconds_created{method="GET"} 1.7e9
python_gc_objects_collected_total{generation="0"} 99
"""


class _Response:
    def __init__(self, *, data=None, text="", status_code=200):
        self._data = data or {}
        self.text = text
        self.status_code = status_code
        self.ok = 200 <= status_code < 300

    def json(self):
        return self._data


class _Registry:
    def list_models(self):
        return [
            {
                "Model": "Demo",
                "Version": "1",
                "Stage": "Production",
                "Description": "Example model",
            }
        ]


class _Service:
    service_url = "https://gateway.test"
    user = "gateway-user"
    pw = "gateway-password"

    def get_registry(self):
        return _Registry()


def _fake_get(url, **kwargs):
    assert kwargs["auth"] == ("gateway-user", "gateway-password")
    assert kwargs["verify"] is False
    if url.endswith("/cache"):
        return _Response(
            data={
                "cache": {"max_models": 10, "ttl_days": 10},
                "cached_models": [
                    {
                        "model_uri": "models:/Demo/1",
                        "num_calls": 9,
                        "loaded_at": "2026-07-15T10:00:00",
                        "last_call": "2026-07-15T11:00:00",
                        "idle_days": 0.25,
                    }
                ],
            }
        )
    return _Response(text=METRICS)


def test_parse_and_describe_gateway(monkeypatch):
    monkeypatch.setattr(mlflow_gateway.requests, "get", _fake_get)

    result = mlflow_gateway.describe_gateway(_Service())

    assert result.success
    assert result.data["models"][0]["Model"] == "Demo"
    assert result.data["summary"] == {
        "requests": 12.0,
        "predictions": 9.0,
        "prediction_errors": 2.0,
        "cache_hits": 7.0,
        "cache_misses": 2.0,
        "cached_models": 1,
    }
    assert all(
        row["name"].startswith("mlox_gateway_")
        for row in result.data["metrics"]
    )


def test_clear_gateway_cache(monkeypatch):
    monkeypatch.setattr(
        mlflow_gateway.requests,
        "delete",
        lambda *args, **kwargs: _Response(data={"cleared_models_count": 3}),
    )

    result = mlflow_gateway.clear_gateway_cache(_Service())

    assert result.success
    assert result.message == "Cleared 3 cached model(s)."


class _PanelApp(App):
    def __init__(self, panel):
        super().__init__()
        self.panel = panel

    def compose(self) -> ComposeResult:
        yield self.panel


async def _render_panel(monkeypatch) -> tuple[int, int, int, str, bool, int]:
    monkeypatch.setattr(mlflow_gateway.requests, "get", _fake_get)
    panel = MLflowGatewaySettingsPanel(None, None, _Service())
    app = _PanelApp(panel)
    async with app.run_test() as pilot:
        await pilot.pause(0.2)
        model_rows = panel.query_one("#mlflow-gateway-models", DataTable).row_count
        cache_rows = panel.query_one("#mlflow-gateway-cache", DataTable).row_count
        metric_rows = panel.query_one("#mlflow-gateway-metrics", DataTable).row_count
        status = str(panel.query_one("#mlflow-gateway-status", Static).content)
        has_outer_scrollbar = panel.show_vertical_scrollbar
        action_height = panel.query_one("#mlflow-gateway-refresh").region.height
    return (
        model_rows,
        cache_rows,
        metric_rows,
        status,
        has_outer_scrollbar,
        action_height,
    )


def test_gateway_panel_renders_models_cache_and_metrics(monkeypatch):
    model_rows, cache_rows, metric_rows, status, outer_scrollbar, action_height = (
        asyncio.run(_render_panel(monkeypatch))
    )

    assert model_rows == 1
    assert cache_rows == 1
    assert metric_rows == 5
    assert "loaded" in status.lower()
    assert outer_scrollbar is False
    assert action_height > 0


async def _remove_panel_during_load(monkeypatch) -> None:
    started = threading.Event()
    finish = threading.Event()

    def delayed_result(_service):
        started.set()
        finish.wait(timeout=2)
        return mlflow_gateway.describe_gateway(SimpleNamespace(service_url=""))

    monkeypatch.setattr(gateway_tui, "describe_gateway", delayed_result)
    panel = MLflowGatewaySettingsPanel(None, None, _Service())
    app = _PanelApp(panel)
    async with app.run_test() as pilot:
        await pilot.pause(0.05)
        assert started.wait(timeout=1)
        await panel.remove()
        finish.set()
        await pilot.pause(0.1)


def test_gateway_panel_ignores_result_after_it_is_removed(monkeypatch):
    asyncio.run(_remove_panel_during_load(monkeypatch))


def test_settings_returns_gateway_panel():
    panel = settings(None, None, SimpleNamespace())
    assert isinstance(panel, MLflowGatewaySettingsPanel)
