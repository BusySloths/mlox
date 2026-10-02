from __future__ import annotations

import asyncio

from textual.app import App, ComposeResult
from types import SimpleNamespace

from textual.widgets import DataTable, Select, Static

from mlox.tui.screens.dashboard.operations_panel import OperationsPanel


class OperationsTestApp(App):
    def __init__(self, infrastructure=None):
        super().__init__()
        self.workspace = SimpleNamespace(infrastructure=infrastructure)

    def compose(self) -> ComposeResult:
        yield OperationsPanel()


async def _incident_view() -> tuple[str, str]:
    app = OperationsTestApp()
    async with app.run_test() as pilot:
        panel = app.query_one(OperationsPanel)
        panel._show_snapshot(
            {
                "active": True,
                "state": "incident",
                "model_name": "demo",
                "runs": 11,
                "baseline_runs": 10,
                "baseline_target": 10,
                "latest_rmse": 5.0,
                "culprit": "demo/pipeline/pca.transform",
                "steps": [
                    {
                        "name": "pca.transform",
                        "depth": 2,
                        "state": "anomalous",
                        "observations": [
                            {
                                "name": "output.mean",
                                "baseline": 0.1,
                                "current": 12.1,
                                "anomalous": True,
                            }
                        ],
                    }
                ],
            }
        )
        await pilot.pause()
        row = " ".join(
            str(cell)
            for cell in app.query_one("#operations-pipeline", DataTable).get_row_at(0)
        )
        evidence = str(app.query_one("#operations-evidence", Static).content)
        return row, evidence


def test_operations_panel_visualizes_pipeline_culprit() -> None:
    row, evidence = asyncio.run(_incident_view())

    assert "pca.transform" in row
    assert "ANOMALOUS" in row
    assert "demo/pipeline/pca.transform" in evidence


async def _monitor_selector() -> tuple[list[tuple[str, str]], str]:
    first = SimpleNamespace(
        name="Monitor A",
        uuid="monitor-a",
        state="running",
        get_telemetry_data=lambda _bundle: "",
    )
    second = SimpleNamespace(
        name="Monitor B",
        uuid="monitor-b",
        state="stopped",
        get_telemetry_data=lambda _bundle: "",
    )
    infrastructure = SimpleNamespace(
        bundles=[
            SimpleNamespace(
                name="one",
                server=SimpleNamespace(ip="10.0.0.1"),
                services=[first],
            ),
            SimpleNamespace(
                name="two",
                server=SimpleNamespace(ip="10.0.0.2"),
                services=[second],
            ),
        ]
    )
    app = OperationsTestApp(infrastructure)
    async with app.run_test() as pilot:
        panel = app.query_one(OperationsPanel)
        panel._load_monitor_options()
        await pilot.pause()
        select = app.query_one("#operations-monitor", Select)
        options = [
            (str(prompt), str(value))
            for prompt, value in select._options
            if value is not Select.NULL
        ]
        return options, str(select.value)


def test_operations_panel_lists_and_defaults_monitor_selector() -> None:
    options, selected = asyncio.run(_monitor_selector())

    assert options == [
        ("Monitor A — 10.0.0.1 (running, monitor-a)", "monitor-a"),
        ("Monitor B — 10.0.0.2 (stopped, monitor-b)", "monitor-b"),
    ]
    assert selected == "monitor-a"
