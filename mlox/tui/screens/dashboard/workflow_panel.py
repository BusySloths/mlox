"""Project workflow orchestrator overview panel."""

from __future__ import annotations

from typing import Any, Optional

from rich.text import Text
from textual import on
from textual.app import ComposeResult
from textual.containers import Container, Horizontal, Vertical
from textual.reactive import reactive
from textual.screen import ModalScreen
from textual.widgets import Button, DataTable, Label, Select, Static

from mlox.application.use_cases.workflows import (
    add_workflow_repository,
    describe_workflow_secret_managers,
    describe_workflows,
    expose_secret_manager_to_workflow_orchestrator,
)
from mlox.tui.services.setup import github_repo
from mlox.tui.template_forms import TemplateSetupDialog

from .model import SelectionInfo


class WorkflowSecretManagerDialog(ModalScreen[str | None]):
    """Modal prompt for selecting a workflow secret manager."""

    def __init__(
        self,
        managers: list[dict[str, Any]],
        selected_manager_id: str = "",
    ) -> None:
        super().__init__()
        self.managers = managers
        self.selected_manager_id = selected_manager_id

    def compose(self) -> ComposeResult:
        with Container(id="workflow-secret-manager-dialog"):
            yield Label("Expose Secret Manager", id="workflow-secret-manager-title")
            if self.managers:
                yield Static(
                    "Select the secret manager DAGs should access.",
                    id="workflow-secret-manager-description",
                )
                yield Select(
                    self._options(),
                    value=self._default_value(),
                    allow_blank=False,
                    id="workflow-secret-manager-select",
                )
            else:
                yield Static(
                    "No available keyfile-exportable secret managers were found.",
                    id="workflow-secret-manager-description",
                )
            with Horizontal(id="workflow-secret-manager-actions"):
                yield Button("Cancel", id="cancel-workflow-secret-manager")
                yield Button(
                    "Expose",
                    id="confirm-workflow-secret-manager",
                    variant="success",
                    disabled=not bool(self.managers),
                )

    @on(Button.Pressed, "#cancel-workflow-secret-manager")
    def handle_cancel(self, _: Button.Pressed) -> None:
        self.dismiss(None)

    @on(Button.Pressed, "#confirm-workflow-secret-manager")
    def handle_confirm(self, _: Button.Pressed) -> None:
        if not self.managers:
            self.dismiss(None)
            return
        select = self.query_one("#workflow-secret-manager-select", Select)
        value = select.value
        if value is Select.BLANK:
            self.dismiss(None)
            return
        self.dismiss(str(value))

    def _options(self) -> list[tuple[str, str]]:
        return [
            (
                f"{manager.get('name', manager.get('id', '-'))} "
                f"({manager.get('kind', '-')})",
                str(manager.get("id", "")),
            )
            for manager in self.managers
            if str(manager.get("id", ""))
        ]

    def _default_value(self):
        values = {value for _, value in self._options()}
        if self.selected_manager_id in values:
            return self.selected_manager_id
        return next(iter(values), Select.BLANK)


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
                yield Button("Add DAG Repo", id="add-workflow-repo")
                yield Button(
                    "Expose Secret Manager",
                    id="expose-workflow-secret-manager",
                )
                yield Button("Refresh Workflows", id="refresh-workflows")
            with Horizontal(id="workflow-browser"):
                orchestrator_table = DataTable(id="workflow-orchestrator-table")
                orchestrator_table.cursor_type = "row"
                orchestrator_table.add_columns(
                    "Orchestrator",
                    "Bundle",
                    "State",
                    "DAGs",
                    "Repos",
                    "Secrets",
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

    @on(Button.Pressed, "#add-workflow-repo")
    def handle_add_workflow_repo(self, _: Button.Pressed) -> None:
        if not self._selected_orchestrator_id:
            self.notify("Select a workflow orchestrator first.", severity="warning")
            return
        workspace = getattr(self.app, "workspace", None)
        infra = getattr(workspace, "infrastructure", None)
        orchestrator = self._selected_orchestrator()
        bundle = orchestrator.get("bundle_ref") if orchestrator else None
        spec = github_repo(infra, bundle, None)
        self.app.push_screen(
            TemplateSetupDialog(spec),
            lambda values: self._add_workflow_repo_from_values(spec, values),
        )

    @on(Button.Pressed, "#expose-workflow-secret-manager")
    def handle_expose_secret_manager(self, _: Button.Pressed) -> None:
        if not self._selected_orchestrator_id:
            self.notify("Select a workflow orchestrator first.", severity="warning")
            return
        self._load_secret_manager_options()

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
        self._set_action_loading(False)
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
                str(orchestrator.get("repository_count", 0)),
                str(orchestrator.get("secret_manager_status", "Not exposed")),
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

    def _add_workflow_repo_from_values(self, spec, values: dict[str, str] | None) -> None:
        if values is None:
            return
        workspace = getattr(self.app, "workspace", None)
        infra = getattr(workspace, "infrastructure", None)
        orchestrator_id = self._selected_orchestrator_id
        try:
            params = spec.params(values, infra)
        except Exception as exc:
            self.notify(f"Could not prepare repository: {exc}", severity="error")
            return

        self._set_action_loading(True)

        def add_repo() -> None:
            result = add_workflow_repository(workspace, orchestrator_id, params)
            self.app.call_from_thread(self._finish_workflow_action, result)

        self.app.run_worker(
            add_repo,
            thread=True,
            exclusive=True,
            group="workflow-add-repository",
        )

    def _load_secret_manager_options(self) -> None:
        workspace = getattr(self.app, "workspace", None)
        orchestrator_id = self._selected_orchestrator_id
        self._set_action_loading(True)

        def load_options() -> None:
            result = describe_workflow_secret_managers(workspace, orchestrator_id)
            self.app.call_from_thread(self._show_secret_manager_dialog, result)

        self.app.run_worker(
            load_options,
            thread=True,
            exclusive=True,
            group="workflow-secret-manager-options",
        )

    def _show_secret_manager_dialog(self, result) -> None:
        self._set_action_loading(False)
        if not result.success:
            self.notify(result.message, severity="error")
            return
        payload = result.data or {}
        dialog = WorkflowSecretManagerDialog(
            list(payload.get("managers", [])),
            str(payload.get("selected_manager_id") or ""),
        )
        self.app.push_screen(dialog, self._expose_selected_secret_manager)

    def _expose_selected_secret_manager(self, manager_id: str | None) -> None:
        if not manager_id:
            return
        workspace = getattr(self.app, "workspace", None)
        orchestrator_id = self._selected_orchestrator_id
        self._set_action_loading(True)

        def expose() -> None:
            result = expose_secret_manager_to_workflow_orchestrator(
                workspace,
                orchestrator_id,
                manager_id,
            )
            self.app.call_from_thread(self._finish_workflow_action, result)

        self.app.run_worker(
            expose,
            thread=True,
            exclusive=True,
            group="workflow-expose-secret-manager",
        )

    def _finish_workflow_action(self, result) -> None:
        self._set_action_loading(False)
        if not result.success:
            self.notify(result.message, severity="error")
            self.load(refresh=True)
            return
        self.notify(result.message)
        self.load(refresh=True)

    def _set_action_loading(self, loading: bool) -> None:
        for selector in (
            "#add-workflow-repo",
            "#expose-workflow-secret-manager",
            "#refresh-workflows",
        ):
            self.query_one(selector, Button).disabled = loading

    def _selected_orchestrator(self) -> dict[str, Any] | None:
        for orchestrator in self._orchestrators:
            if str(orchestrator.get("id") or "") == self._selected_orchestrator_id:
                return orchestrator
        return None

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
