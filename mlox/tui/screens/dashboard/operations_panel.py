"""Live model-pipeline operations watch panel."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import json
from typing import Any, Optional

from rich.text import Text
from textual import on
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.css.query import NoMatches
from textual.reactive import reactive
from textual.screen import ModalScreen
from textual.widgets import (
    Button,
    DataTable,
    Input,
    Select,
    Static,
    TabbedContent,
    TabPane,
)

from mlox.application.use_cases.operations import (
    OPERATIONS_BOARD_TITLE,
    OperationsWatchSession,
    get_operations_board,
    list_operations_monitors,
    load_operations_reasoning_settings,
    reason_about_operations_incident,
    refresh_operations_watch,
    save_operations_postmortem,
    save_operations_reasoning_settings,
    start_operations_watch,
)
from mlox.project.entries import Entry, lane_color, parse_board
from mlox.project.operations import OperationsEvent

from .model import SelectionInfo


def _pipeline_detail_rows(details: dict[str, Any]) -> list[tuple[str, str, str]]:
    def value_text(value: Any) -> str:
        if isinstance(value, (dict, list, tuple)):
            return json.dumps(value, sort_keys=True, default=str)
        return str(value) if value not in (None, "") else "-"

    rows: list[tuple[str, str, str]] = []
    for field in (
        "pipeline_id",
        "pipeline_name",
        "trace_id",
        "span_id",
        "request_id",
        "model_name",
        "model_version",
        "model_alias",
        "started_ns",
    ):
        rows.append(("run", field, value_text(details.get(field))))
    for key, value in sorted((details.get("labels") or {}).items()):
        rows.append(("run label", str(key), value_text(value)))
    for index, step in enumerate(details.get("steps") or [], start=1):
        scope = f"step {index}: {step.get('name', '-')}"
        for field in ("path", "span_id", "depth", "started_ns"):
            rows.append((scope, field, value_text(step.get(field))))
        for key, value in sorted((step.get("labels") or {}).items()):
            rows.append((f"{scope} label", str(key), value_text(value)))
        for key, value in sorted((step.get("observations") or {}).items()):
            rows.append((f"{scope} observation", str(key), value_text(value)))
    return rows


class PipelineDetailsDialog(ModalScreen[None]):
    """Display one immutable snapshot of the selected pipeline's latest run."""

    def __init__(self, pipeline: dict[str, Any]) -> None:
        super().__init__()
        self.pipeline = deepcopy(pipeline)

    def compose(self) -> ComposeResult:
        with Vertical(id="operations-details-dialog"):
            yield Static(
                f"Pipeline details: {self.pipeline.get('pipeline_name', '-')}",
                id="operations-details-title",
            )
            table = DataTable(id="operations-details-table")
            table.cursor_type = "row"
            table.add_columns("Scope", "Field", "Value")
            yield table
            yield Button("Close", id="close-operations-details", variant="primary")

    def on_mount(self) -> None:
        table = self.query_one("#operations-details-table", DataTable)
        for row in _pipeline_detail_rows(self.pipeline.get("details") or {}):
            table.add_row(*row)

    @on(Button.Pressed, "#close-operations-details")
    def handle_close(self, _: Button.Pressed) -> None:
        self.dismiss(None)


class OperationsPlanBoard(Horizontal):
    """Read-only projection of the Operations board stored in Knowledge."""

    def show_entry(self, entry: Entry | None) -> None:
        self.remove_children()
        if entry is None:
            self.mount(
                Static(
                    "No Knowledge board named 'Operations' exists yet.",
                    classes="operations-plan-empty",
                )
            )
            return
        widgets: list[Static] = []
        for column in parse_board(entry.body_md):
            text = Text()
            if not column.items:
                text.append("(empty)", style="dim italic")
            for item in column.items:
                text.append("✓ " if item.checked else "· ", style="dim" if item.checked else "")
                text.append(item.text + "\n", style="dim" if item.checked else "")
            widget = Static(text, classes="operations-plan-column")
            color = lane_color(column.name)
            widget.border_title = Text(column.name, style=f"bold {color}")
            widget.styles.border = ("round", color)
            widgets.append(widget)
        if widgets:
            self.mount(*widgets)
        else:
            self.mount(
                Static(
                    "The Operations board has no markdown columns.",
                    classes="operations-plan-empty",
                )
            )


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
        self._pipeline_states: dict[str, str] = {}
        self._activity: list[OperationsEvent] = []
        self._operations_board: Entry | None = None

    def compose(self) -> ComposeResult:
        with Vertical(id="operations-content"):
            with TabbedContent(id="operations-tabs"):
                with TabPane("Incidents", id="operations-incidents-tab"):
                    with Horizontal(id="operations-incident-actions"):
                        yield Static(
                            "Watcher is stopped.", id="operations-watch-summary"
                        )
                        yield Button(
                            "Get Details",
                            id="operations-get-details",
                            disabled=True,
                        )
                        yield Button(
                            "Acknowledge",
                            id="operations-acknowledge",
                            disabled=True,
                        )
                        yield Button(
                            "Recommend Action",
                            id="operations-recommend-action",
                            disabled=True,
                        )
                        yield Button(
                            "Save Postmortem",
                            id="operations-save-postmortem",
                            disabled=True,
                        )
                    pipelines = DataTable(id="operations-pipelines")
                    pipelines.cursor_type = "row"
                    pipelines.add_columns(
                        "Pipeline",
                        "Model / version",
                        "Runs / baseline",
                        "Quality",
                        "State",
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
                    yield Static("", id="operations-remediation")
                    yield Static(
                        "Start watching, then send healthy traffic to establish a baseline.",
                        id="operations-evidence",
                    )
                with TabPane("Plan", id="operations-plan-tab"):
                    with Horizontal(id="operations-plan-actions"):
                        yield Static(
                            "Knowledge board: Operations",
                            id="operations-plan-title",
                        )
                        yield Button("Reload", id="operations-plan-reload")
                        yield Button(
                            "Create Operations Board",
                            id="operations-plan-create",
                        )
                        yield Button(
                            "Open in Knowledge",
                            id="operations-plan-open-knowledge",
                            disabled=True,
                        )
                    yield OperationsPlanBoard(id="operations-plan-board")
                    yield Static("", id="operations-plan-status")
                with TabPane("Activity", id="operations-activity-tab"):
                    with Horizontal(id="operations-activity-actions"):
                        yield Static(
                            "Immutable project operations history",
                            id="operations-activity-title",
                        )
                        yield Button("Reload", id="operations-activity-reload")
                    activity = DataTable(id="operations-activity")
                    activity.cursor_type = "row"
                    activity.add_columns(
                        "Timestamp", "Actor", "Event", "Target", "Status", "Summary"
                    )
                    yield activity
                    yield Static(
                        "Detection, acknowledgement, remediation, recovery and review "
                        "events are persisted in the project audit trail.",
                        id="operations-activity-help",
                    )
                with TabPane("Settings", id="operations-settings-tab"):
                    with VerticalScroll(id="operations-settings-scroll"):
                        yield Static("Telemetry watcher", classes="operations-heading")
                        with Horizontal(id="operations-source"):
                            yield Static(
                                "Telemetry monitor", id="operations-source-label"
                            )
                            yield Select(
                                options=[],
                                prompt="Select telemetry monitor",
                                id="operations-monitor",
                            )
                        yield Static(
                            "The first 10 completed runs per pipeline are assumed normal.",
                            id="operations-assumption",
                        )
                        with Horizontal(id="operations-actions"):
                            yield Button(
                                "Start Watching",
                                id="start-operations",
                                variant="success",
                            )
                            yield Button(
                                "Stop Watching",
                                id="stop-operations",
                                variant="warning",
                            )
                            yield Button("Reset", id="reset-operations")
                        yield Static(
                            "Reasoning assistant", classes="operations-heading"
                        )
                        yield Static(
                            "Detection remains deterministic. The assistant is advisory "
                            "and cannot execute remediation without approval.",
                            classes="operations-settings-help",
                        )
                        with Horizontal(classes="operations-setting-row"):
                            yield Static("Mode", classes="operations-setting-label")
                            yield Select(
                                [
                                    ("Disabled", "disabled"),
                                    ("Advisory", "advisory"),
                                    ("Approval required", "approval"),
                                ],
                                value="disabled",
                                allow_blank=False,
                                id="operations-reasoning-mode",
                            )
                        with Horizontal(classes="operations-setting-row"):
                            yield Static("Provider", classes="operations-setting-label")
                            yield Select(
                                [("OpenAI compatible", "openai-compatible")],
                                value="openai-compatible",
                                allow_blank=False,
                                id="operations-reasoning-provider",
                            )
                        with Horizontal(classes="operations-setting-row"):
                            yield Static("Endpoint", classes="operations-setting-label")
                            yield Input(
                                placeholder="https://…/v1",
                                id="operations-reasoning-endpoint",
                            )
                        with Horizontal(classes="operations-setting-row"):
                            yield Static("Model", classes="operations-setting-label")
                            yield Input(
                                placeholder="Reasoning model name",
                                id="operations-reasoning-model",
                            )
                        with Horizontal(classes="operations-setting-row"):
                            yield Static("API key", classes="operations-setting-label")
                            yield Input(
                                placeholder="Leave blank to keep the stored key",
                                password=True,
                                id="operations-reasoning-api-key",
                            )
                        with Horizontal(id="operations-reasoning-actions"):
                            yield Button(
                                "Save Reasoning Settings",
                                id="operations-save-reasoning",
                                variant="primary",
                            )
                            yield Static("", id="operations-reasoning-status")

    def on_mount(self) -> None:
        self.watch_selection(self.selection)
        self._show_snapshot(self._empty_snapshot())
        self._load_plan()
        self._load_activity()
        self._load_reasoning_settings()

    def watch_selection(self, selection: Optional[SelectionInfo]) -> None:
        if not self.is_mounted:
            return
        self.display = bool(selection and selection.type == "root")
        if self.display:
            self._load_monitor_options()
            self._load_plan()
            self._load_activity()
            self._load_reasoning_settings()

    @on(TabbedContent.TabActivated, "#operations-tabs")
    def handle_operations_tab_activated(
        self, event: TabbedContent.TabActivated
    ) -> None:
        tab_id = event.tab.id
        if tab_id == "operations-plan-tab":
            self._load_plan()
        elif tab_id == "operations-activity-tab":
            self._load_activity()
        elif tab_id == "operations-settings-tab":
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
        monitor_name = getattr(self._session, "monitor_name", "telemetry monitor")
        self._record_activity(
            "watch_started",
            f"Started watching {monitor_name}.",
            target=str(getattr(self._session, "monitor_uuid", "")),
            status="active",
        )
        self.app.notify(result.message)

    @on(Button.Pressed, "#stop-operations")
    def handle_stop(self, _: Button.Pressed) -> None:
        if self._session is not None:
            self._session.stop()
            self._show_snapshot(self._session.snapshot())
        if self._watch_timer is not None:
            self._watch_timer.pause()
        self.query_one("#operations-monitor", Select).disabled = False
        self._record_activity(
            "watch_stopped",
            "Stopped the telemetry watcher.",
            status="stopped",
        )

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
        self._pipeline_states.clear()
        self.query_one("#operations-get-details", Button).disabled = True
        self.query_one("#operations-monitor", Select).disabled = False
        self._show_snapshot(self._empty_snapshot())
        self._record_activity(
            "watch_reset",
            "Reset the in-memory baseline and incident state.",
            actor="user",
        )

    @on(DataTable.RowSelected, "#operations-pipelines")
    def handle_pipeline_selected(self, event: DataTable.RowSelected) -> None:
        pipeline_id = str(event.row_key.value)
        pipeline = self._pipeline_snapshots.get(pipeline_id)
        if pipeline is None:
            return
        self._selected_pipeline_id = pipeline_id
        self._populate_pipeline(pipeline.get("steps") or [])
        self.query_one("#operations-get-details", Button).disabled = not bool(
            pipeline.get("details")
        )
        self._update_incident_actions(pipeline)
        self._show_evidence(pipeline)

    @on(Button.Pressed, "#operations-get-details")
    def handle_get_details(self, _: Button.Pressed) -> None:
        pipeline = self._pipeline_snapshots.get(self._selected_pipeline_id)
        if pipeline and pipeline.get("details"):
            self.app.push_screen(PipelineDetailsDialog(pipeline))

    @on(Button.Pressed, "#operations-acknowledge")
    def handle_acknowledge(self, _: Button.Pressed) -> None:
        pipeline = self._selected_pipeline()
        if pipeline is None:
            return
        self._record_activity(
            "incident_acknowledged",
            f"Acknowledged the incident for {pipeline.get('pipeline_name', 'pipeline')}.",
            actor="user",
            target=str(pipeline.get("id") or ""),
            status="acknowledged",
        )
        self.app.notify("Incident acknowledged.")

    @on(Button.Pressed, "#operations-recommend-action")
    def handle_recommend_action(self, _: Button.Pressed) -> None:
        pipeline = self._selected_pipeline()
        if pipeline is None:
            return
        self.query_one("#operations-recommend-action", Button).disabled = True

        def reason() -> None:
            result = reason_about_operations_incident(
                getattr(self.app, "workspace", None), deepcopy(pipeline)
            )
            self.app.call_from_thread(
                self._finish_recommend_action, deepcopy(pipeline), result
            )

        self.app.run_worker(
            reason,
            thread=True,
            exclusive=True,
            group="operations-reasoning",
        )

    def _finish_recommend_action(self, pipeline, result) -> None:
        culprit = str(pipeline.get("culprit") or "the affected pipeline")
        if result.success:
            payload = result.data or {}
            recommendation = str(payload.get("recommendation") or "")
            actor = "reasoning-assistant"
            status = (
                "approval-required"
                if payload.get("mode") == "approval"
                else "advisory"
            )
            details = {"model": payload.get("model"), "execution": "manual"}
        else:
            recommendation = (
                "Disable corrupted traffic, preserve the current evidence snapshot, "
                f"and verify that rolling observations recover after {culprit}."
            )
            actor = "system"
            status = "manual-runbook"
            details = {
                "culprit": culprit,
                "execution": "manual",
                "reasoning_fallback": result.message,
            }
        self.query_one("#operations-remediation", Static).update(
            f"Recommended manual remediation: {recommendation}"
        )
        self._record_activity(
            "remediation_proposed",
            recommendation,
            actor=actor,
            target=str(pipeline.get("id") or ""),
            status=status,
            details=details,
        )
        self._update_incident_actions(self._selected_pipeline())
        self.app.notify("A manual remediation was proposed; no action was executed.")

    @on(Button.Pressed, "#operations-save-postmortem")
    def handle_save_postmortem(self, _: Button.Pressed) -> None:
        pipeline = self._selected_pipeline()
        workspace = getattr(self.app, "workspace", None)
        if pipeline is None or workspace is None:
            return
        result = save_operations_postmortem(workspace, pipeline, self._activity)
        if not result.success:
            self.app.notify(result.message, severity="error")
            return
        self._record_activity(
            "postmortem_saved",
            result.message,
            actor="user",
            target=str(pipeline.get("id") or ""),
            status="reviewed",
        )
        self._load_plan()
        self.app.notify(result.message)

    def _selected_pipeline(self) -> dict[str, Any] | None:
        return self._pipeline_snapshots.get(self._selected_pipeline_id)

    def _load_plan(self) -> None:
        if not self.is_mounted:
            return
        workspace = getattr(self.app, "workspace", None)
        result = get_operations_board(workspace)
        board = (result.data or {}).get("board") if result.success else None
        self._operations_board = board
        self.query_one("#operations-plan-board", OperationsPlanBoard).show_entry(board)
        self.query_one("#operations-plan-status", Static).update(result.message)
        self.query_one("#operations-plan-create", Button).display = board is None
        self.query_one("#operations-plan-open-knowledge", Button).disabled = board is None

    @on(Button.Pressed, "#operations-plan-reload")
    def handle_plan_reload(self, _: Button.Pressed) -> None:
        self._load_plan()

    @on(Button.Pressed, "#operations-plan-create")
    def handle_plan_create(self, _: Button.Pressed) -> None:
        workspace = getattr(self.app, "workspace", None)
        result = get_operations_board(workspace, create=True)
        if not result.success:
            self.app.notify(result.message, severity="error")
            return
        self._load_plan()
        self._record_activity(
            "operations_board_created",
            "Created the Operations planning board in Knowledge.",
            actor="user",
            target=OPERATIONS_BOARD_TITLE,
        )
        self.app.notify(result.message)

    @on(Button.Pressed, "#operations-plan-open-knowledge")
    def handle_plan_open_knowledge(self, _: Button.Pressed) -> None:
        if self._operations_board is None:
            return
        try:
            main_tabs = self.app.query_one("#main-tabs", TabbedContent)
            main_tabs.active = "knowledge-tab"
            from .knowledge_panel import KnowledgePanel

            self.app.query_one(KnowledgePanel).open_entry_by_title(
                self._operations_board.title
            )
        except NoMatches:
            self.app.notify(
                "The Knowledge panel is unavailable in this view.", severity="warning"
            )

    def _load_activity(self) -> None:
        if not self.is_mounted:
            return
        workspace = getattr(self.app, "workspace", None)
        list_events = getattr(workspace, "list_operations_events", None)
        if callable(list_events):
            try:
                self._activity = list(list_events(200))
            except Exception as exc:
                self.app.notify(f"Could not load operations activity: {exc}", severity="error")
        self._populate_activity()

    def _populate_activity(self) -> None:
        table = self.query_one("#operations-activity", DataTable)
        table.clear(columns=False)
        for event in self._activity:
            table.add_row(
                event.created_at,
                event.actor,
                event.event_type.replace("_", " "),
                event.target or "-",
                event.status,
                event.summary,
                key=event.id or None,
            )

    def _record_activity(
        self,
        event_type: str,
        summary: str,
        *,
        actor: str = "system",
        target: str = "",
        status: str = "recorded",
        details: dict[str, Any] | None = None,
    ) -> OperationsEvent:
        event = OperationsEvent(
            event_type=event_type,
            summary=summary,
            actor=actor,
            target=target,
            status=status,
            details=details or {},
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        workspace = getattr(self.app, "workspace", None)
        record = getattr(workspace, "record_operations_event", None)
        if callable(record):
            try:
                event = record(event)
            except Exception as exc:
                self.app.notify(f"Could not persist operations activity: {exc}", severity="error")
        self._activity.insert(0, event)
        self._activity = self._activity[:200]
        self._populate_activity()
        return event

    @on(Button.Pressed, "#operations-activity-reload")
    def handle_activity_reload(self, _: Button.Pressed) -> None:
        self._load_activity()

    def _load_reasoning_settings(self) -> None:
        if not self.is_mounted:
            return
        workspace = getattr(self.app, "workspace", None)
        result = load_operations_reasoning_settings(workspace)
        status = self.query_one("#operations-reasoning-status", Static)
        status.update(result.message)
        if not result.success:
            return
        settings = result.data or {}
        self.query_one("#operations-reasoning-mode", Select).value = str(
            settings.get("mode") or "disabled"
        )
        self.query_one("#operations-reasoning-provider", Select).value = str(
            settings.get("provider") or "openai-compatible"
        )
        self.query_one("#operations-reasoning-endpoint", Input).value = str(
            settings.get("endpoint") or ""
        )
        self.query_one("#operations-reasoning-model", Input).value = str(
            settings.get("model") or ""
        )
        if settings.get("api_key_configured"):
            status.update("Reasoning settings loaded; an API key is stored securely.")

    @on(Button.Pressed, "#operations-save-reasoning")
    def handle_save_reasoning(self, _: Button.Pressed) -> None:
        workspace = getattr(self.app, "workspace", None)
        mode = self.query_one("#operations-reasoning-mode", Select).value
        provider = self.query_one("#operations-reasoning-provider", Select).value
        result = save_operations_reasoning_settings(
            workspace,
            mode=str(mode),
            provider=str(provider),
            endpoint=self.query_one("#operations-reasoning-endpoint", Input).value,
            model=self.query_one("#operations-reasoning-model", Input).value,
            api_key=self.query_one("#operations-reasoning-api-key", Input).value,
        )
        self.query_one("#operations-reasoning-api-key", Input).value = ""
        self.query_one("#operations-reasoning-status", Static).update(result.message)
        if not result.success:
            self.app.notify(result.message, severity="error")
            return
        self._record_activity(
            "reasoning_settings_updated",
            f"Reasoning assistant mode set to {mode}.",
            actor="user",
            status="configured",
        )
        self.app.notify(result.message)

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
        self.query_one("#operations-get-details", Button).disabled = not bool(
            (selected or {}).get("details")
        )
        self._update_incident_actions(selected)
        self._record_pipeline_state_changes(pipelines)
        active = bool(snapshot.get("active"))
        state = str(snapshot.get("state") or "stopped")
        self.query_one("#operations-watch-summary", Static).update(
            f"Watcher: {'active' if active else 'stopped'} · Overall state: {state}"
        )
        self._show_evidence(selected or snapshot)

    def _update_incident_actions(self, pipeline: dict[str, Any] | None) -> None:
        state = str((pipeline or {}).get("state") or "")
        has_pipeline = pipeline is not None
        self.query_one("#operations-acknowledge", Button).disabled = state != "incident"
        self.query_one("#operations-recommend-action", Button).disabled = state not in {
            "incident",
            "recovered",
        }
        self.query_one("#operations-save-postmortem", Button).disabled = not (
            has_pipeline and state == "recovered"
        )

    def _record_pipeline_state_changes(
        self, pipelines: list[dict[str, Any]]
    ) -> None:
        for pipeline in pipelines:
            pipeline_id = str(pipeline.get("id") or "")
            state = str(pipeline.get("state") or "")
            previous = self._pipeline_states.get(pipeline_id)
            if not pipeline_id or not state or previous == state:
                continue
            self._pipeline_states[pipeline_id] = state
            name = str(pipeline.get("pipeline_name") or "model pipeline")
            if state == "incident":
                culprit = str(pipeline.get("culprit") or "unknown origin")
                self._record_activity(
                    "incident_detected",
                    f"Detected an anomaly in {name}; likely origin: {culprit}.",
                    target=pipeline_id,
                    status="open",
                    details={"culprit": culprit},
                )
            elif state == "recovered":
                self._record_activity(
                    "incident_recovered",
                    f"Rolling observations for {name} returned to baseline.",
                    target=pipeline_id,
                    status="recovered",
                )
            elif previous is not None:
                self._record_activity(
                    "pipeline_state_changed",
                    f"{name} changed from {previous} to {state}.",
                    target=pipeline_id,
                    status=state,
                )

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
