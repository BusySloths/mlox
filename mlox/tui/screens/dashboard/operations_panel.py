"""Live model-pipeline operations watch panel."""

from __future__ import annotations

from typing import Any, Optional

from rich.text import Text
from textual import on
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.reactive import reactive
from textual.widgets import Button, DataTable, Static

from mlox.application.use_cases.operations import (
    OperationsWatchSession,
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

    def compose(self) -> ComposeResult:
        with Vertical(id="operations-content"):
            with Horizontal(id="operations-summary"):
                yield Static(id="operations-state", classes="operations-metric")
                yield Static(id="operations-model", classes="operations-metric")
                yield Static(id="operations-runs", classes="operations-metric")
                yield Static(id="operations-rmse", classes="operations-metric")
            with Horizontal(id="operations-actions"):
                yield Static(
                    "The first 10 completed runs after Start are assumed normal.",
                    id="operations-assumption",
                )
                yield Button("Start Watching", id="start-operations", variant="success")
                yield Button("Stop Watching", id="stop-operations", variant="warning")
                yield Button("Reset", id="reset-operations")
            table = DataTable(id="operations-pipeline")
            table.cursor_type = "row"
            table.add_columns("Pipeline step", "Baseline", "Current", "State")
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

    @on(Button.Pressed, "#start-operations")
    def handle_start(self, _: Button.Pressed) -> None:
        workspace = getattr(self.app, "workspace", None)
        infra = getattr(workspace, "infrastructure", None)
        self.query_one("#start-operations", Button).disabled = True

        def start() -> None:
            result = start_operations_watch(infra)
            self.app.call_from_thread(self._finish_start, result)

        self.app.run_worker(start, thread=True, exclusive=True, group="operations-start")

    def _finish_start(self, result) -> None:
        self.query_one("#start-operations", Button).disabled = False
        if not result.success:
            self.app.notify(result.message, severity="error")
            return
        payload = result.data or {}
        self._session = payload.get("session")
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

    @on(Button.Pressed, "#reset-operations")
    def handle_reset(self, _: Button.Pressed) -> None:
        self._session = None
        if self._watch_timer is not None:
            self._watch_timer.stop()
            self._watch_timer = None
        self.query_one("#operations-pipeline", DataTable).clear(columns=False)
        self._show_snapshot(self._empty_snapshot())

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
        }

    def _show_snapshot(self, snapshot: dict[str, Any]) -> None:
        state = str(snapshot.get("state") or "stopped")
        display_state = state if snapshot.get("active") else "stopped"
        colors = {
            "stopped": "grey70",
            "calibrating": "bright_yellow",
            "watching": "bright_green",
            "incident": "bright_red",
            "recovered": "bright_cyan",
        }
        self._metric(
            "#operations-state",
            "State",
            display_state.title(),
            colors.get(display_state, "white"),
        )
        self._metric(
            "#operations-model", "Model", str(snapshot.get("model_name") or "-"), "cyan"
        )
        baseline = int(snapshot.get("baseline_runs") or 0)
        target = int(snapshot.get("baseline_target") or 10)
        self._metric(
            "#operations-runs",
            "Runs / baseline",
            f"{snapshot.get('runs', 0)} / {baseline}/{target}",
            "bright_green" if baseline >= target else "bright_yellow",
        )
        rmse = snapshot.get("latest_rmse")
        self._metric(
            "#operations-rmse",
            "Latest RMSE",
            "-" if rmse is None else f"{float(rmse):.4f}",
            "bright_red" if state == "incident" else "bright_green",
        )
        self._populate_pipeline(snapshot.get("steps") or [])
        self._show_evidence(snapshot)

    def _metric(self, selector: str, label: str, value: str, color: str) -> None:
        text = Text()
        text.append(f"{value}\n", style=f"bold {color}")
        text.append(label, style="dim")
        self.query_one(selector, Static).update(text)

    def _populate_pipeline(self, rows: list[dict[str, Any]]) -> None:
        table = self.query_one("#operations-pipeline", DataTable)
        table.clear(columns=False)
        for index, row in enumerate(rows):
            observations = row.get("observations") or []
            focus = next(
                (item for item in observations if item.get("anomalous")),
                next(
                    (item for item in observations if item.get("name") == "rmse.value"),
                    observations[0] if observations else None,
                ),
            )
            baseline = "-" if not focus else f"{float(focus['baseline']):.4f}"
            current = "-" if not focus else f"{float(focus['current']):.4f}"
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
            table.add_row(label, baseline, current, state_text)

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
