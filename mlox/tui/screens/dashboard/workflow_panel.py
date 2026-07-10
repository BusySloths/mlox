"""Project workflow orchestrator overview panel."""

from __future__ import annotations

from typing import Any, Optional

from rich.text import Text
from textual import on
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.reactive import reactive
from textual.widgets import Button, DataTable, Static

from mlox.application.use_cases.workflows import describe_workflows

from .model import SelectionInfo


class WorkflowPanel(Static):
    """Root-level workflow orchestrator and DAG browser."""

    selection: reactive[Optional[SelectionInfo]] = reactive(None)

    def __init__(self, *children, **kwargs) -> None:
        super().__init__(*children, **kwargs)
        self._orchestrators: list[dict[str, Any]] = []
        self._workflows_by_orchestrator: dict[str, list[dict[str, Any]]] = {}
        self._orchestrator_ids: list[str] = []
        self._selected_orchestrator_id = ""

    def compose(self) -> ComposeResult:
        with Vertical(id="workflow-content"):
            with Horizontal(id="workflow-metrics"):
                yield Static(
                    id="workflow-metric-orchestrators",
                    classes="workflow-metric",
                )
                yield Static(id="workflow-metric-running", classes="workflow-metric")
                yield Static(id="workflow-metric-dags", classes="workflow-metric")
                yield Static(id="workflow-metric-active", classes="workflow-metric")
            with Horizontal(id="workflow-actions"):
                yield Static("Project Workflows", id="workflow-title")
                yield Button("Refresh Workflows", id="refresh-workflows")
            with Horizontal(id="workflow-browser"):
                orchestrator_table = DataTable(id="workflow-orchestrator-table")
                orchestrator_table.cursor_type = "row"
                orchestrator_table.add_columns(
                    "Orchestrator",
                    "Bundle",
                    "State",
                    "DAGs",
                    "Message",
                )
                yield orchestrator_table

                dag_table = DataTable(id="workflow-dag-table")
                dag_table.cursor_type = "row"
                dag_table.add_columns(
                    "DAG",
                    "Schedule",
                    "Paused",
                    "Active",
                    "Last Run",
                    "Last State",
                    "Last End",
                    "Owners",
                )
                yield dag_table

    @property
    def orchestrator_table(self) -> DataTable:
        return self.query_one("#workflow-orchestrator-table", DataTable)

    @property
    def dag_table(self) -> DataTable:
        return self.query_one("#workflow-dag-table", DataTable)

    def on_mount(self) -> None:
        self.watch_selection(self.selection)

    def watch_selection(self, selection: Optional[SelectionInfo]) -> None:
        if not self.is_mounted:
            return
        if not selection or selection.type != "root":
            self.display = False
            return
        self.display = True
        self.load()

    @on(Button.Pressed, "#refresh-workflows")
    def handle_refresh(self, _: Button.Pressed) -> None:
        self.load(refresh=True)

    @on(DataTable.RowSelected, "#workflow-orchestrator-table")
    def handle_orchestrator_selected(self, event: DataTable.RowSelected) -> None:
        self._select_orchestrator(self._row_key(event))

    def load(self, refresh: bool = False) -> None:
        workspace = getattr(self.app, "workspace", None)
        infra = getattr(workspace, "infrastructure", None)
        self._set_loading(refresh)

        def load_workflows() -> None:
            result = describe_workflows(infra)
            self.app.call_from_thread(self._show_result, result)

        self.app.run_worker(
            load_workflows,
            thread=True,
            exclusive=True,
            group="project-workflows",
        )

    def _show_result(self, result) -> None:
        if not self.selection or self.selection.type != "root":
            return
        button = self.query_one("#refresh-workflows", Button)
        button.disabled = False
        button.label = "Refresh Workflows"
        if not result.success:
            self._orchestrators = []
            self._workflows_by_orchestrator = {}
            self._populate_orchestrators()
            self._update_metrics()
            self.dag_table.add_row("-", "-", "-", "-", "-", "-", "-", result.message)
            return

        payload = result.data or {}
        self._orchestrators = list(payload.get("orchestrators", []))
        self._workflows_by_orchestrator = dict(
            payload.get("workflows_by_orchestrator", {})
        )
        self._populate_orchestrators()
        self._update_metrics(payload.get("metrics"))
        if self._orchestrator_ids:
            self._select_orchestrator(self._orchestrator_ids[0])
        else:
            self.dag_table.clear(columns=False)
            self.dag_table.add_row(
                "-",
                "-",
                "-",
                "-",
                "-",
                "-",
                "-",
                "No workflows found.",
            )

    def _set_loading(self, refresh: bool) -> None:
        button = self.query_one("#refresh-workflows", Button)
        button.disabled = True
        button.label = "Refreshing..." if refresh else "Loading..."
        self._orchestrators = []
        self._workflows_by_orchestrator = {}
        self._orchestrator_ids = []
        self._selected_orchestrator_id = ""
        self.orchestrator_table.clear(columns=False)
        self.dag_table.clear(columns=False)
        self.dag_table.add_row(
            "-",
            "-",
            "-",
            "-",
            "-",
            "-",
            "-",
            "Loading workflows...",
        )
        self._update_metrics()

    def _populate_orchestrators(self) -> None:
        table = self.orchestrator_table
        table.clear(columns=False)
        self._orchestrator_ids = []
        if not self._orchestrators:
            table.add_row("-", "-", "-", "-", "No workflow orchestrators found.")
            return

        for orchestrator in self._orchestrators:
            orchestrator_id = str(orchestrator.get("id") or "")
            if not orchestrator_id:
                continue
            self._orchestrator_ids.append(orchestrator_id)
            table.add_row(
                str(orchestrator.get("name", "-")),
                str(orchestrator.get("bundle", "-")),
                self._state_badge(str(orchestrator.get("state", "unknown"))),
                str(orchestrator.get("workflow_count", 0)),
                str(orchestrator.get("message") or ""),
                key=orchestrator_id,
            )
        if self._orchestrator_ids:
            table.cursor_coordinate = (0, 0)

    def _select_orchestrator(self, orchestrator_id: str) -> None:
        if orchestrator_id not in self._orchestrator_ids:
            return
        self._selected_orchestrator_id = orchestrator_id
        workflows = self._workflows_by_orchestrator.get(orchestrator_id, [])
        self._populate_workflows(workflows)

    def _populate_workflows(self, workflows: list[dict[str, Any]]) -> None:
        table = self.dag_table
        table.clear(columns=False)
        if not workflows:
            table.add_row("-", "-", "-", "-", "-", "-", "-", "No DAGs found.")
            return
        for index, workflow in enumerate(workflows):
            table.add_row(
                str(workflow.get("name", "-")),
                str(workflow.get("schedule", "-")),
                self._bool_badge(workflow.get("is_paused")),
                self._bool_badge(workflow.get("is_active")),
                str(workflow.get("last_run_start") or "-"),
                self._run_state_badge(str(workflow.get("last_run_state") or "-")),
                str(workflow.get("last_run_end") or "-"),
                str(workflow.get("owners") or workflow.get("message") or ""),
                key=str(index),
            )
        table.cursor_coordinate = (0, 0)

    def _update_metrics(self, metrics: dict[str, Any] | None = None) -> None:
        metrics = metrics or {}
        values = [
            (
                "#workflow-metric-orchestrators",
                "Orchestrators",
                metrics.get("orchestrators", len(self._orchestrators)),
                "cyan",
            ),
            (
                "#workflow-metric-running",
                "Running",
                metrics.get(
                    "running_orchestrators",
                    sum(
                        1
                        for row in self._orchestrators
                        if row.get("state") == "running"
                    ),
                ),
                "green",
            ),
            (
                "#workflow-metric-dags",
                "DAGs",
                metrics.get(
                    "workflows",
                    sum(len(rows) for rows in self._workflows_by_orchestrator.values()),
                ),
                "bright_green",
            ),
            (
                "#workflow-metric-active",
                "Active DAGs",
                metrics.get("active_workflows", 0),
                "bright_blue",
            ),
        ]
        for selector, label, value, color in values:
            text = Text()
            text.append(f"{value}\n", style=f"bold {color}")
            text.append(label, style="dim")
            self.query_one(selector, Static).update(text)

    def _state_badge(self, state: str) -> Text:
        style = {
            "running": "bold white on dark_green",
            "starting": "bold black on bright_yellow",
            "failed": "bold white on dark_red",
            "stopped": "bold white on grey23",
            "unknown": "bold white on grey23",
        }.get(state, "bold white on dark_blue")
        return Text(f" {state} ", style=style)

    def _run_state_badge(self, state: str) -> Text:
        style = {
            "success": "bold white on dark_green",
            "running": "bold black on bright_yellow",
            "queued": "bold white on dark_blue",
            "failed": "bold white on dark_red",
            "upstream_failed": "bold white on dark_red",
            "-": "dim",
        }.get(state, "bold white on grey23")
        if state == "-":
            return Text("-", style=style)
        return Text(f" {state} ", style=style)

    def _bool_badge(self, value: Any) -> Text:
        if value is True:
            return Text(" yes ", style="bold white on dark_green")
        if value is False:
            return Text(" no ", style="bold white on grey23")
        return Text("N/A", style="dim")

    def _row_key(self, event: DataTable.RowSelected) -> str:
        row_key = getattr(event.row_key, "value", event.row_key)
        return str(row_key)
