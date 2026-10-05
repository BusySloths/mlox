from __future__ import annotations

import asyncio

from textual.app import App, ComposeResult
from types import SimpleNamespace

from textual.widgets import Button, DataTable, Input, Select, Static

from mlox.application.use_cases.operations import OPERATIONS_REASONING_SECRET
from mlox.project import ProjectWorkspace
from mlox.tui.screens.dashboard.operations_panel import (
    OperationsPanel,
    PipelineDetailsDialog,
)


class OperationsTestApp(App):
    def __init__(self, infrastructure=None, workspace=None):
        super().__init__()
        self.workspace = workspace or SimpleNamespace(infrastructure=infrastructure)

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


async def _pipeline_summary_view() -> tuple[list[str], list[str], str]:
    app = OperationsTestApp()
    async with app.run_test(size=(160, 50)) as pilot:
        panel = app.query_one(OperationsPanel)
        panel._show_snapshot(
            {
                "active": True,
                "pipelines": [
                    {
                        "id": "forecast",
                        "pipeline_name": "forecasting",
                        "model_name": "forecast",
                        "model_version": "2",
                        "state": "watching",
                        "runs": 12,
                        "baseline_runs": 10,
                        "baseline_target": 10,
                        "quality_name": "rmse.mean",
                        "quality_value": 0.1234,
                        "steps": [],
                        "details": {
                            "pipeline_id": "pipeline-123",
                            "pipeline_name": "forecasting",
                            "trace_id": "trace-456",
                            "span_id": "root-span",
                            "request_id": "request-789",
                            "model_name": "forecast",
                            "model_version": "2",
                            "model_alias": "champion",
                            "started_ns": 123456,
                            "labels": {"deployment.environment": "demo"},
                            "steps": [
                                {
                                    "name": "normalize",
                                    "path": "forecast/pipeline/normalize",
                                    "span_id": "step-span",
                                    "depth": 2,
                                    "started_ns": 123457,
                                    "labels": {"mlox.step.kind": "normalization"},
                                    "observations": {"output.mean": 0.2},
                                }
                            ],
                        },
                    },
                    {
                        "id": "ranking",
                        "pipeline_name": "ranking",
                        "model_name": "ranker",
                        "model_version": "7",
                        "state": "calibrating",
                        "runs": 4,
                        "baseline_runs": 4,
                        "baseline_target": 10,
                        "quality_name": "accuracy.mean",
                        "quality_value": 0.91,
                        "steps": [],
                    },
                ],
            }
        )
        await pilot.pause()
        table = app.query_one("#operations-pipelines", DataTable)
        details_button = app.query_one("#operations-get-details", Button)
        assert not details_button.disabled
        panel.handle_get_details(Button.Pressed(details_button))
        await pilot.pause()
        dialog = app.screen
        assert isinstance(dialog, PipelineDetailsDialog)
        details = dialog.query_one("#operations-details-table", DataTable)
        panel._pipeline_snapshots["forecast"]["details"]["request_id"] = (
            "newer-request"
        )
        detail_text = "\n".join(
            " | ".join(str(cell) for cell in details.get_row_at(index))
            for index in range(details.row_count)
        )
        await pilot.click("#close-operations-details")
        return (
            [str(cell) for cell in table.get_row_at(0)],
            [str(cell) for cell in table.get_row_at(1)],
            detail_text,
        )


def test_operations_panel_summarizes_each_pipeline_in_table() -> None:
    forecast, ranking, details = asyncio.run(_pipeline_summary_view())

    assert "forecasting" in forecast
    assert "forecast / 2" in forecast
    assert "rmse.mean: 0.1234" in forecast
    assert "ranking" in ranking
    assert "accuracy.mean: 0.9100" in ranking
    assert "pipeline_id | pipeline-123" in details
    assert "request_id | request-789" in details
    assert "newer-request" not in details
    assert "step 1: normalize observation | output.mean | 0.2" in details


def test_operations_plan_activity_and_reasoning_settings_share_project_state(
    tmp_path,
) -> None:
    workspace = ProjectWorkspace.create(str(tmp_path / "operations-ui"), "pw")
    app = OperationsTestApp(workspace=workspace)

    async def run() -> None:
        async with app.run_test(size=(160, 50)) as pilot:
            panel = app.query_one(OperationsPanel)
            create = app.query_one("#operations-plan-create", Button)
            panel.handle_plan_create(Button.Pressed(create))
            await pilot.pause()

            assert workspace.find_entry_by_title("Operations", "board") is not None
            assert not app.query_one(
                "#operations-plan-open-knowledge", Button
            ).disabled

            app.query_one("#operations-reasoning-mode", Select).value = "advisory"
            app.query_one("#operations-reasoning-endpoint", Input).value = (
                "https://llm.example/v1"
            )
            app.query_one("#operations-reasoning-model", Input).value = "reasoner"
            app.query_one("#operations-reasoning-api-key", Input).value = "secret"
            save = app.query_one("#operations-save-reasoning", Button)
            panel.handle_save_reasoning(Button.Pressed(save))
            await pilot.pause()

            stored = workspace.secrets.load_secret(OPERATIONS_REASONING_SECRET)
            assert stored["api_key"] == "secret"
            assert stored["mode"] == "advisory"
            assert app.query_one("#operations-reasoning-api-key", Input).value == ""
            assert workspace.list_operations_events()
            assert app.query_one("#operations-activity", DataTable).row_count >= 2

    asyncio.run(run())


def test_incident_lifecycle_persists_audit_and_postmortem(tmp_path) -> None:
    workspace = ProjectWorkspace.create(str(tmp_path / "incident-ui"), "pw")
    app = OperationsTestApp(workspace=workspace)

    async def run() -> None:
        async with app.run_test(size=(160, 50)) as pilot:
            panel = app.query_one(OperationsPanel)
            pipeline = {
                "id": "demo\x1f1\x1foperations-demo",
                "pipeline_name": "operations-demo",
                "model_name": "demo",
                "model_version": "1",
                "state": "incident",
                "runs": 11,
                "baseline_runs": 10,
                "baseline_target": 10,
                "quality_name": "rmse.mean",
                "quality_value": 4.2,
                "culprit": "demo/pipeline/pca.transform",
                "steps": [],
                "details": {"pipeline_id": "pipeline-demo"},
            }
            panel._show_snapshot({"active": True, "pipelines": [pipeline]})
            acknowledge = app.query_one("#operations-acknowledge", Button)
            panel.handle_acknowledge(Button.Pressed(acknowledge))

            recovered = {**pipeline, "state": "recovered", "quality_value": 0.1}
            panel._show_snapshot({"active": True, "pipelines": [recovered]})
            save = app.query_one("#operations-save-postmortem", Button)
            assert not save.disabled
            panel.handle_save_postmortem(Button.Pressed(save))
            await pilot.pause()

            event_types = {
                event.event_type for event in workspace.list_operations_events()
            }
            assert {
                "incident_detected",
                "incident_acknowledged",
                "incident_recovered",
                "postmortem_saved",
            } <= event_types
            postmortems = workspace.list_entries("wiki")
            assert len(postmortems) == 1
            assert "pca.transform" in postmortems[0].body_md
            board = workspace.find_entry_by_title("Operations", "board")
            assert postmortems[0].title in board.body_md

    asyncio.run(run())
