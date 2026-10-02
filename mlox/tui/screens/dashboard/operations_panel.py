"""Live model-pipeline operations watch panel."""

from __future__ import annotations

from typing import Any, Optional

from rich.text import Text
from textual import on
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.reactive import reactive
from textual.widgets import Button, DataTable, Select, Static

from mlox.application.use_cases.operations import (
    OperationsWatchSession,
    list_operations_monitors,
    refresh_operations_watch,
    start_operations_watch,
)

from .model import SelectionInfo


class OperationsPanel(Static):
    """Calibrate and watch one telemetry-discovered model pipeline."""

    selection: reactive[Optional[SelectionInfo]] = reactive(None)

    def __init__(self, *children, **kwargs) -> None:
        super().__init__(*children, **kwargs)
        self._session: OperationsWatchSession | None = None
        self._refreshing = False
        self._watch_timer = None
        self._pipeline_snapshots: dict[str, dict[str, Any]] = {}
        self._selected_pipeline_id = ""

    def compose(self) -> ComposeResult:
        with Vertical(id="operations-content"):
            with Horizontal(id="operations-source"):
                yield Static("Telemetry monitor", id="operations-source-label")
                yield Select(
                    options=[],
                    prompt="Select telemetry monitor",
                    id="operations-monitor",
                )
            with Horizontal(id="operations-actions"):
                yield Static(
                    "The first 10 completed runs per pipeline are assumed normal.",
                    id="operations-assumption",
                )
                yield Button("Start Watching", id="start-operations", variant="success")
                yield Button("Stop Watching", id="stop-operations", variant="warning")
                yield Button("Reset", id="reset-operations")
            pipelines = DataTable(id="operations-pipelines")
            pipelines.cursor_type = "row"
            pipelines.add_columns(
                "Pipeline", "Model / version", "Runs / baseline", "Quality", "State"
            )
            yield pipelines
            table = DataTable(id="operations-pipeline")
            table.cursor_type = "row"
            table.add_columns(
                "Pipeline step",
                "Baseline",
                "Current",
                "1 min / 5 avg",
                "5 min / 10 avg",
                "State",
            )
            yield table
            yield Static(
                "Start watching, then send healthy traffic to establish a baseline.",
                id="operations-evidence",
            )

    def on_mount(self) -> None:
        self.watch_selection(self.selection)
        self._show_snapshot(self._empty_snapshot())

    def watch_selection(self, selection: Optional[SelectionInfo]) -> None:
        if not self.is_mounted:
            return
        self.display = bool(selection and selection.type == "root")
        if self.display:
            self._load_monitor_options()

    def _load_monitor_options(self) -> None:
        workspace = getattr(self.app, "workspace", None)
        infra = getattr(workspace, "infrastructure", None)
        select = self.query_one("#operations-monitor", Select)
        current = None if select.value is Select.BLANK else str(select.value)
        monitors = list_operations_monitors(infra)
        options = [
            (
                f"{monitor['name']} — {monitor['server']} "
                f"({monitor['state']}, {monitor['uuid']})",
                monitor["uuid"],
            )
            for monitor in monitors
            if monitor["uuid"]
        ]
        select.set_options(options)
        available = {value for _, value in options}
        if current in available:
            select.value = current
        elif options:
            select.value = options[0][1]
        else:
            select.clear()

    @on(Button.Pressed, "#start-operations")
    def handle_start(self, _: Button.Pressed) -> None:
        workspace = getattr(self.app, "workspace", None)
        infra = getattr(workspace, "infrastructure", None)
        monitor = self.query_one("#operations-monitor", Select)
        monitor_uuid = None if monitor.value is Select.BLANK else str(monitor.value)
        if not monitor_uuid:
            self.app.notify("Select a telemetry monitor first.", severity="error")
            return
        self.query_one("#start-operations", Button).disabled = True

        def start() -> None:
            result = start_operations_watch(infra, monitor_uuid=monitor_uuid)
            self.app.call_from_thread(self._finish_start, result)

        self.app.run_worker(start, thread=True, exclusive=True, group="operations-start")

    def _finish_start(self, result) -> None:
        self.query_one("#start-operations", Button).disabled = False
        if not result.success:
            self.app.notify(result.message, severity="error")
            return
        payload = result.data or {}
        self._session = payload.get("session")
        self.query_one("#operations-monitor", Select).disabled = True
        if self._watch_timer is None:
            self._watch_timer = self.set_interval(2.0, self._refresh_if_active)
        else:
            self._watch_timer.resume()
        self._show_snapshot(payload.get("snapshot") or self._empty_snapshot())
        self.app.notify(result.message)

    @on(Button.Pressed, "#stop-operations")
    def handle_stop(self, _: Button.Pressed) -> None:
        if self._session is not None:
            self._session.stop()
            self._show_snapshot(self._session.snapshot())
        if self._watch_timer is not None:
            self._watch_timer.pause()
        self.query_one("#operations-monitor", Select).disabled = False

    @on(Button.Pressed, "#reset-operations")
    def handle_reset(self, _: Button.Pressed) -> None:
        self._session = None
        if self._watch_timer is not None:
            self._watch_timer.stop()
            self._watch_timer = None
        self.query_one("#operations-pipeline", DataTable).clear(columns=False)
        self.query_one("#operations-pipelines", DataTable).clear(columns=False)
        self._pipeline_snapshots.clear()
        self._selected_pipeline_id = ""
        self.query_one("#operations-monitor", Select).disabled = False
        self._show_snapshot(self._empty_snapshot())

    @on(DataTable.RowSelected, "#operations-pipelines")
    def handle_pipeline_selected(self, event: DataTable.RowSelected) -> None:
        pipeline_id = str(event.row_key.value)
        pipeline = self._pipeline_snapshots.get(pipeline_id)
        if pipeline is None:
            return
        self._selected_pipeline_id = pipeline_id
        self._populate_pipeline(pipeline.get("steps") or [])
        self._show_evidence(pipeline)

    def _refresh_if_active(self) -> None:
        if not self._session or not self._session.active or self._refreshing:
            return
        workspace = getattr(self.app, "workspace", None)
        infra = getattr(workspace, "infrastructure", None)
        self._refreshing = True

        def refresh() -> None:
            result = refresh_operations_watch(infra, self._session)
            self.app.call_from_thread(self._finish_refresh, result)

        self.app.run_worker(
            refresh,
            thread=True,
            exclusive=True,
            group="operations-refresh",
        )

    def _finish_refresh(self, result) -> None:
        self._refreshing = False
        if not result.success:
            self.app.notify(result.message, severity="error")
            return
        self._show_snapshot((result.data or {}).get("snapshot") or {})

    @staticmethod
    def _empty_snapshot() -> dict[str, Any]:
        return {
            "active": False,
            "state": "stopped",
            "model_name": "-",
            "runs": 0,
            "baseline_runs": 0,
            "baseline_target": 10,
            "steps": [],
            "culprit": "",
            "latest_rmse": None,
            "baseline_rmse": None,
            "pipelines": [],
        }

    def _show_snapshot(self, snapshot: dict[str, Any]) -> None:
        pipelines = snapshot.get("pipelines") or []
        if not pipelines and snapshot.get("steps"):
            pipelines = [
                {
                    "id": "legacy-pipeline",
                    "pipeline_name": snapshot.get("pipeline_name") or "model pipeline",
                    "model_name": snapshot.get("model_name") or "-",
                    "model_version": snapshot.get("model_version") or "-",
                    "state": snapshot.get("state") or "stopped",
                    "runs": snapshot.get("runs") or 0,
                    "baseline_runs": snapshot.get("baseline_runs") or 0,
                    "baseline_target": snapshot.get("baseline_target") or 10,
                    "quality_name": "rmse.mean"
                    if snapshot.get("latest_rmse") is not None
                    else "",
                    "quality_value": snapshot.get("latest_rmse"),
                    "steps": snapshot.get("steps") or [],
                    "culprit": snapshot.get("culprit") or "",
                }
            ]
        self._populate_pipelines(pipelines, active=bool(snapshot.get("active")))
        selected = self._pipeline_snapshots.get(self._selected_pipeline_id)
        if selected is None and pipelines:
            selected = pipelines[0]
            self._selected_pipeline_id = str(selected.get("id") or "")
        self._populate_pipeline((selected or {}).get("steps") or [])
        self._show_evidence(selected or snapshot)

    def _populate_pipelines(
        self, pipelines: list[dict[str, Any]], *, active: bool
    ) -> None:
        table = self.query_one("#operations-pipelines", DataTable)
        table.clear(columns=False)
        self._pipeline_snapshots = {
            str(pipeline.get("id") or index): pipeline
            for index, pipeline in enumerate(pipelines)
        }
        for pipeline_id, pipeline in self._pipeline_snapshots.items():
            state = str(pipeline.get("state") or "stopped") if active else "stopped"
            quality_name = str(pipeline.get("quality_name") or "")
            quality_value = pipeline.get("quality_value")
            quality = (
                "-"
                if quality_value is None
                else f"{quality_name}: {float(quality_value):.4f}"
            )
            state_text = Text(
                f" {state.upper()} ",
                style=(
                    "bold white on dark_red"
                    if state == "incident"
                    else "bold white on dark_green"
                    if state in {"watching", "recovered"}
                    else "bold black on yellow"
                    if state == "calibrating"
                    else "dim"
                ),
            )
            table.add_row(
                str(pipeline.get("pipeline_name") or "-"),
                f"{pipeline.get('model_name', '-')} / {pipeline.get('model_version', '-')}",
                f"{pipeline.get('runs', 0)} / {pipeline.get('baseline_runs', 0)}/"
                f"{pipeline.get('baseline_target', 10)}",
                quality,
                state_text,
                key=pipeline_id,
            )

    def _populate_pipeline(self, rows: list[dict[str, Any]]) -> None:
        table = self.query_one("#operations-pipeline", DataTable)
        table.clear(columns=False)
        for index, row in enumerate(rows):
            observations = row.get("observations") or []
            focus = next(
                (item for item in observations if item.get("anomalous")),
                next(
                    (item for item in observations if item.get("name") == "rmse.value"),
                    next(
                        (
                            item
                            for item in observations
                            if item.get("name") == "rmse.mean"
                        ),
                        observations[0] if observations else None,
                    ),
                ),
            )
            baseline = "-" if not focus else f"{float(focus['baseline']):.4f}"
            current = "-" if not focus else f"{float(focus['current']):.4f}"
            short_window = (
                "-"
                if not focus or focus.get("short_window") is None
                else f"{float(focus['short_window']):.4f}"
            )
            long_window = (
                "-"
                if not focus or focus.get("long_window") is None
                else f"{float(focus['long_window']):.4f}"
            )
            depth = max(0, int(row.get("depth") or 1) - 1)
            branch = "└─ " if index == len(rows) - 1 else "├─ "
            label = f"{'  ' * depth}{branch if depth else ''}{row.get('name', '-')}"
            state = str(row.get("state") or "normal")
            state_text = Text(
                " ANOMALOUS " if state == "anomalous" else " NORMAL ",
                style=(
                    "bold white on dark_red"
                    if state == "anomalous"
                    else "bold white on dark_green"
                ),
            )
            table.add_row(
                label, baseline, current, short_window, long_window, state_text
            )

    def _show_evidence(self, snapshot: dict[str, Any]) -> None:
        state = snapshot.get("state")
        culprit = str(snapshot.get("culprit") or "")
        if state == "calibrating":
            message = (
                f"Calibrating: {snapshot.get('baseline_runs', 0)}/"
                f"{snapshot.get('baseline_target', 10)} assumed-normal runs collected."
            )
        elif state == "incident":
            message = (
                f"Likely origin: {culprit}. This is the first pipeline step whose "
                "observations deviate from the captured baseline."
                if culprit
                else "An anomaly is present in the observed pipeline."
            )
        elif state == "recovered":
            message = "Observed values returned to the captured baseline after an incident."
        elif state == "watching":
            message = "Baseline complete. Watching new model runs for deviations."
        else:
            message = "Start watching, then send healthy traffic to establish a baseline."
        self.query_one("#operations-evidence", Static).update(message)
