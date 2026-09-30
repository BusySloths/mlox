from __future__ import annotations

import asyncio

from textual.app import App, ComposeResult
from textual.widgets import DataTable, Static

from mlox.tui.screens.dashboard.operations_panel import OperationsPanel


class OperationsTestApp(App):
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
