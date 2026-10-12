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
    add_operations_plan_item,
    archive_operations_agent,
    ask_operations_agent,
    execute_operations_remediation,
    get_operations_board,
    list_operations_monitors,
    list_operations_agents,
    load_operations_reasoning_settings,
    reason_about_operations_incident,
    refresh_operations_watch,
    save_operations_postmortem,
    save_operations_agent,
    save_operations_reasoning_settings,
    set_operations_agent_status,
    start_operations_watch,
)
from mlox.project.entries import Entry, lane_color, parse_board
from mlox.project.operations import (
    OperationsAgentMessage,
    OperationsAgentRun,
    OperationsAgentProposal,
    OperationsEvent,
)

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
        "subject_kind",
        "subject_name",
        "subject_version",
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
        for field in ("path", "span_id", "depth", "started_ns", "duration_ms"):
            rows.append((scope, field, value_text(step.get(field))))
        for key, value in sorted((step.get("labels") or {}).items()):
            rows.append((f"{scope} label", str(key), value_text(value)))
        for key, value in sorted((step.get("observations") or {}).items()):
            rows.append((f"{scope} observation", str(key), value_text(value)))
    return rows


class PipelineDetailsDialog(ModalScreen[None]):
    """Display one immutable snapshot of the selected workload's latest run."""

    def __init__(self, pipeline: dict[str, Any]) -> None:
        super().__init__()
        self.pipeline = deepcopy(pipeline)

    def compose(self) -> ComposeResult:
        with Vertical(id="operations-details-dialog"):
            yield Static(
                f"Workload details: {self.pipeline.get('pipeline_name', '-')}",
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


class OperationsAgentDialog(ModalScreen[dict[str, str] | None]):
    """Create a stored role profile without activating an agent runtime."""

    def compose(self) -> ComposeResult:
        with Vertical(id="operations-agent-dialog"):
            yield Static("ADD TEAM MEMBER", id="operations-agent-title")
            yield Input(placeholder="Team member name", id="operations-agent-name")
            yield Select(
                [(role, role) for role in ("Investigator", "Planner", "Executor", "Auditor")],
                prompt="Select role",
                id="operations-agent-role",
            )
            with Horizontal(id="operations-agent-actions"):
                yield Button("Add agent", id="operations-agent-save", variant="primary")

    @on(Button.Pressed, "#operations-agent-save")
    def handle_save(self, _: Button.Pressed) -> None:
        role = self.query_one("#operations-agent-role", Select).value
        self.dismiss(
            {"name": self.query_one("#operations-agent-name", Input).value,
             "role": "" if role is Select.BLANK else str(role)}
        )


class OperationsAgentWorkspace(Vertical):
    """The selected team member's durable conversation and proposal workspace."""

    def __init__(self, *children, **kwargs) -> None:
        super().__init__(*children, **kwargs)
        self.agent: dict[str, Any] | None = None

    def compose(self) -> ComposeResult:
        yield Static("Latest conversation", classes="operations-agent-workspace-label")
        messages = DataTable(id="operations-agent-workspace-messages")
        messages.cursor_type = "row"
        messages.add_columns("When", "From", "Type", "Message")
        yield messages
        yield Static("Latest proposals", classes="operations-agent-workspace-label")
        proposals = DataTable(id="operations-agent-workspace-proposals")
        proposals.cursor_type = "row"
        proposals.add_columns("When", "Proposal", "Status", "Summary")
        yield proposals
        yield Input(
            placeholder="Assign a focused work package or leave a question…",
            id="operations-agent-workspace-input",
            disabled=True,
        )
        with Horizontal(id="operations-agent-workspace-actions"):
            yield Button(
                "Assign work", id="operations-agent-workspace-assign", disabled=True
            )
            yield Button(
                "Ask question", id="operations-agent-workspace-question", disabled=True
            )

    def show_agent(self, agent: dict[str, Any]) -> None:
        """Make a roster member active without navigating away from Team."""

        self.agent = deepcopy(agent)
        unavailable = agent.get("status") in {"archived", "disabled", "inactive"}
        self.query_one("#operations-agent-workspace-input", Input).disabled = unavailable
        self.query_one("#operations-agent-workspace-assign", Button).disabled = unavailable
        self.query_one("#operations-agent-workspace-question", Button).disabled = unavailable
        self._load_history()

    def _load_history(self) -> None:
        agent_id = str((self.agent or {}).get("id") or "")
        messages_table = self.query_one("#operations-agent-workspace-messages", DataTable)
        proposals_table = self.query_one("#operations-agent-workspace-proposals", DataTable)
        messages_table.clear(columns=False)
        proposals_table.clear(columns=False)
        workspace = getattr(self.app, "workspace", None)
        list_messages = getattr(workspace, "list_operations_agent_messages", None)
        list_proposals = getattr(workspace, "list_operations_agent_proposals", None)
        try:
            messages = list_messages(agent_id) if callable(list_messages) else []
            proposals = list_proposals(agent_id) if callable(list_proposals) else []
        except Exception:
            messages, proposals = [], []
        for message in reversed(messages):
            messages_table.add_row(
                str(message.created_at)[:19], message.author, message.kind,
                message.content.replace("\n", " ")[:180],
            )
        for proposal in proposals:
            proposals_table.add_row(
                str(proposal.created_at)[:19], proposal.headline, proposal.status,
                proposal.description.replace("\n", " ")[:180],
                key=proposal.id,
            )

    @on(Button.Pressed, "#operations-agent-workspace-assign")
    @on(Button.Pressed, "#operations-agent-workspace-question")
    def handle_assign(self, event: Button.Pressed) -> None:
        instruction = self.query_one("#operations-agent-workspace-input", Input).value.strip()
        if not instruction:
            self.app.notify("Describe the work package first.", severity="warning")
            return
        if self.agent is None:
            self.app.notify("Select a team member first.", severity="warning")
            return
        workspace = getattr(self.app, "workspace", None)
        save_run = getattr(workspace, "save_operations_agent_run", None)
        record_message = getattr(workspace, "record_operations_agent_message", None)
        if not callable(save_run) or not callable(record_message):
            self.app.notify("Project workspace is unavailable.", severity="error")
            return
        try:
            is_question = event.button.id == "operations-agent-workspace-question"
            run = save_run(
                OperationsAgentRun(
                    agent_id=str(self.agent.get("id") or ""),
                    summary=("Question: " if is_question else "") + instruction,
                    status="question" if is_question else "queued",
                )
            )
            record_message(
                OperationsAgentMessage(
                    run_id=run.id,
                    author="user",
                    kind="question" if is_question else "instruction",
                    content=instruction,
                )
            )
        except Exception as exc:
            self.app.notify(f"Could not assign work: {exc}", severity="error")
            return
        self.query_one("#operations-agent-workspace-input", Input).value = ""
        self._load_history()
        if not is_question:
            self.app.notify("Work package saved to the project.")
            return
        self.query_one("#operations-agent-workspace-question", Button).disabled = True

        def ask() -> None:
            result = ask_operations_agent(
                workspace, agent=deepcopy(self.agent or {}), question=instruction
            )
            self.app.call_from_thread(self._finish_question, run.id, result)

        self.app.run_worker(
            ask, thread=True, exclusive=True, group="operations-agent-question"
        )

    def _finish_question(self, run_id: str, result) -> None:
        workspace = getattr(self.app, "workspace", None)
        record_message = getattr(workspace, "record_operations_agent_message", None)
        save_run = getattr(workspace, "save_operations_agent_run", None)
        if callable(record_message):
            answer = (
                str((result.data or {}).get("answer") or "")
                if result.success
                else str(result.message)
            )
            try:
                record_message(
                    OperationsAgentMessage(
                        run_id=run_id,
                        author=str((self.agent or {}).get("id") or "agent"),
                        kind="answer" if result.success else "error",
                        content=answer,
                    )
                )
                if callable(save_run):
                    save_run(
                        OperationsAgentRun(
                            id=run_id,
                            agent_id=str((self.agent or {}).get("id") or ""),
                            summary=answer[:240],
                            status="answered" if result.success else "failed",
                        )
                    )
            except Exception as exc:
                self.app.notify(f"Could not save agent answer: {exc}", severity="error")
        self.query_one("#operations-agent-workspace-question", Button).disabled = False
        self._load_history()
        self.app.notify(result.message, severity="information" if result.success else "error")


class RecommendationDialog(ModalScreen[str | None]):
    """Review a compact reasoning proposal before any plan or runtime change."""

    def __init__(
        self,
        *,
        headline: str,
        description: str,
        verification: str,
        actions: list[dict[str, Any]],
        mode: str,
    ) -> None:
        super().__init__()
        self.headline = headline
        self.description = description
        self.verification = verification
        self.actions = deepcopy(actions)
        self.mode = mode

    def compose(self) -> ComposeResult:
        with Vertical(id="operations-recommendation-dialog"):
            yield Static("REMEDIATION PROPOSAL", id="operations-recommendation-eyebrow")
            yield Static(self.headline, id="operations-recommendation-title")
            with VerticalScroll(id="operations-recommendation-scroll"):
                yield Static(self.description, id="operations-recommendation-description")
                yield Static("Verification", classes="operations-recommendation-label")
                yield Static(
                    self.verification or "Verify recovery against the rolling telemetry windows.",
                    id="operations-recommendation-verification",
                )
                yield Static("Proposed MLOX actions", classes="operations-recommendation-label")
                actions = DataTable(id="operations-recommendation-actions")
                actions.cursor_type = "row"
                actions.add_columns("Action", "Target", "Effect")
                yield actions
            with Horizontal(id="operations-recommendation-buttons"):
                yield Button("Add to Plan", id="operations-recommendation-add-plan")
                yield Button(
                    "Execute",
                    id="operations-recommendation-execute",
                    variant="warning",
                    disabled=not self.actions or self.mode != "approval",
                )
                yield Button("Dismiss", id="operations-recommendation-dismiss", variant="primary")

    def on_mount(self) -> None:
        table = self.query_one("#operations-recommendation-actions", DataTable)
        if not self.actions:
            table.add_row("No MLOX action proposed", "-", "Review manually")
            return
        labels = {
            "check_service_health": ("Check service health", "Read / verify"),
            "restart_service": ("Restart service", "Restart / repair"),
            "rollback_model_alias": ("Roll back model alias", "Move to earlier version"),
        }
        for action in self.actions:
            name = str(action.get("name") or "MLOX action")
            title, effect = labels.get(name, (name.replace("_", " ").title(), "Execute"))
            arguments = action.get("arguments") or {}
            target = str(
                arguments.get("service_name")
                or (
                    f"{arguments.get('model_name', '-')}:"
                    f"{arguments.get('alias', '-')} → v{arguments.get('target_version', '-')}"
                )
            )
            table.add_row(title, target, effect)

    @on(Button.Pressed, "#operations-recommendation-add-plan")
    def handle_add_plan(self, _: Button.Pressed) -> None:
        self.dismiss("plan")

    @on(Button.Pressed, "#operations-recommendation-execute")
    def handle_execute(self, _: Button.Pressed) -> None:
        self.dismiss("execute")

    @on(Button.Pressed, "#operations-recommendation-dismiss")
    def handle_dismiss(self, _: Button.Pressed) -> None:
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
    """Calibrate and watch telemetry-discovered pipelines and their steps."""

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
        self._postmortem_saved_for: set[str] = set()
        self._observer_completed_for: set[str] = set()
        self._latest_recommendation: dict[str, Any] | None = None
        self._observer_status = "Standing by for a pipeline anomaly."
        self._metric_view = "quality"
        self._agent_rows: list[dict[str, Any]] = []
        self._observer_runs: dict[str, str] = {}

    def compose(self) -> ComposeResult:
        with Vertical(id="operations-content"):
            with Horizontal(id="operations-workspace"):
                with Vertical(id="operations-nav"):
                    yield Static("OPERATIONS", id="operations-nav-title")
                    yield Static("CONTROL ROOM", id="operations-nav-subtitle")
                    yield Button("Team", id="operations-nav-team", classes="operations-nav-active")
                    yield Button("Pipelines", id="operations-nav-pipelines")
                    yield Button("Plan", id="operations-nav-plan")
                    yield Button("Activity", id="operations-nav-activity")
                    yield Button("Settings", id="operations-nav-settings")
                    yield Static(
                        "Observe\nPlan\nRecover",
                        id="operations-nav-footer",
                    )
                with Vertical(id="operations-stage"):
                    with Vertical(id="operations-hero"):
                        yield Static("OPERATIONS CONTROL ROOM", id="operations-eyebrow")
                        yield Static("Incident detective", id="operations-title")
                        yield Static(
                            "Live evidence, safe recommendations, and recovery tracking.",
                            id="operations-subtitle",
                        )
                    yield from self._compose_operations_tabs()

    def _compose_operations_tabs(self) -> ComposeResult:
        with TabbedContent(id="operations-tabs"):
            with TabPane("Team", id="operations-team-tab"):
                with Horizontal(id="operations-team-layout"):
                    with Vertical(id="operations-team-roster-pane"):
                        roster = DataTable(id="operations-team-roster")
                        roster.cursor_type = "row"
                        roster.add_columns("Member", "Role", "Authority", "Status")
                        yield roster
                        with Horizontal(id="operations-team-actions"):
                            yield Button("Add agent", id="operations-team-add")
                            yield Button(
                                "Enable selected",
                                id="operations-team-toggle",
                                disabled=True,
                            )
                            yield Button("Archive selected", id="operations-team-archive")
                        yield Static("Select a team member.", id="operations-team-context")
                        yield Static(
                            "Select a team member to see its project-backed workspace. "
                            "The observer only proposes; it never executes a remediation.",
                            id="operations-team-help",
                        )
                    yield OperationsAgentWorkspace(id="operations-agent-workspace")
            with TabPane("Pipelines", id="operations-pipelines-tab"):
                with Horizontal(id="operations-incident-actions"):
                    yield Static("Watcher is stopped.", id="operations-watch-summary")
                    yield Select(
                        [("Quality", "quality"), ("Execution time", "duration")],
                        value="quality",
                        allow_blank=False,
                        id="operations-metric-view",
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
                        "Investigate",
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
                    "Workload",
                    "Subject / version",
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
                    "Start watching, then send healthy workload runs to establish a baseline.",
                    id="operations-evidence",
                )
            with TabPane("Plan", id="operations-plan-tab"):
                with Horizontal(id="operations-plan-actions"):
                    yield Static("Knowledge board: Operations", id="operations-plan-title")
                    yield Button(
                        "Create Operations Board",
                        id="operations-plan-create",
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
                        yield Static("Telemetry monitor", id="operations-source-label")
                        yield Select(
                            options=[],
                            prompt="Select telemetry monitor",
                            id="operations-monitor",
                        )
                    yield Static(
                        "The first 10 completed runs per workload are assumed normal.",
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
                    yield Static("Reasoning assistant", classes="operations-heading")
                    yield Static(
                        "The Pipeline Observer is advisory-only. Saving a provider, "
                        "endpoint, model and key enables recommendations.",
                        classes="operations-settings-help",
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
        self._activate_operations_section("team")
        self._show_snapshot(self._empty_snapshot())
        self._show_observer_state()
        self._load_agent_roster()
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

    @property
    def watching(self) -> bool:
        """Whether a live session must stay mounted while another tab is visible."""

        return bool(self._session and self._session.active)

    @on(TabbedContent.TabActivated, "#operations-tabs")
    def handle_operations_tab_activated(
        self, _: TabbedContent.TabActivated
    ) -> None:
        tab_id = self.query_one("#operations-tabs", TabbedContent).active
        if tab_id == "operations-plan-tab":
            self._load_plan()
        elif tab_id == "operations-activity-tab":
            self._load_activity()
        elif tab_id == "operations-settings-tab":
            self._load_monitor_options()
        self._show_operations_hero(tab_id)

    @on(Button.Pressed, "#operations-nav-team")
    @on(Button.Pressed, "#operations-nav-pipelines")
    @on(Button.Pressed, "#operations-nav-plan")
    @on(Button.Pressed, "#operations-nav-activity")
    @on(Button.Pressed, "#operations-nav-settings")
    def handle_operations_navigation(self, event: Button.Pressed) -> None:
        section = str(event.button.id or "").removeprefix("operations-nav-")
        self._activate_operations_section(section)

    def _activate_operations_section(self, section: str) -> None:
        tab_id = f"operations-{section}-tab"
        tabs = self.query_one("#operations-tabs", TabbedContent)
        tabs.active = tab_id
        self._show_operations_hero(tab_id)
        for name in ("team", "pipelines", "plan", "activity", "settings"):
            button = self.query_one(f"#operations-nav-{name}", Button)
            button.set_class(name == section, "operations-nav-active")

    def _show_operations_hero(self, tab_id: str) -> None:
        headings = {
            "operations-team-tab": (
                "Operations team",
                "Review agent work, proposals, and questions without leaving Operations.",
            ),
            "operations-pipelines-tab": (
                "Pipelines",
                "Live pipeline evidence, step metrics, and anomaly detection.",
            ),
            "operations-plan-tab": (
                "Operational plan",
                "Turn incidents and decisions into visible, durable follow-up work.",
            ),
            "operations-activity-tab": (
                "Activity & audit",
                "A durable account of what was detected, decided, and reviewed.",
            ),
            "operations-settings-tab": (
                "Watcher & reasoning",
                "Configure telemetry watching and an optional advisory reasoning model.",
            ),
        }
        title, subtitle = headings.get(tab_id, headings["operations-team-tab"])
        self.query_one("#operations-title", Static).update(title)
        self.query_one("#operations-subtitle", Static).update(subtitle)

    def _show_observer_state(self, pipeline: dict[str, Any] | None = None) -> None:
        """Project the bounded observer state into the persistent Team view."""

        # The observer state remains available in Activity and Pipelines; Team is
        # intentionally reserved for agent workspaces and their durable history.
        del pipeline

    def _load_agent_roster(self) -> None:
        result = list_operations_agents(getattr(self.app, "workspace", None))
        table = self.query_one("#operations-team-roster", DataTable)
        table.clear(columns=False)
        self._agent_rows = list((result.data or {}).get("agents") or []) if result.success else []
        for agent in self._agent_rows:
            status = str(agent.get("status") or "-")
            table.add_row(
                str(agent.get("name") or "-"),
                str(agent.get("role") or "-"),
                str(agent.get("scope") or "-"),
                self._status_label(status),
                key=str(agent.get("id") or "agent"),
            )
        if self._agent_rows:
            self._select_agent(self._agent_rows[0])

    @staticmethod
    def _status_label(status: str) -> Text:
        styles = {
            "enabled": "bold #052e16 on #86efac",
            "disabled": "bold #cbd5e1 on #334155",
            "inactive": "bold #cbd5e1 on #334155",
            "archived": "dim #94a3b8 on #1e293b",
        }
        return Text(status.upper(), style=styles.get(status, "#cbd5e1"))

    def _select_agent(self, agent: dict[str, Any]) -> None:
        self.query_one(OperationsAgentWorkspace).show_agent(agent)
        self.query_one("#operations-team-context", Static).update(
            f"{agent.get('name') or 'Operations agent'} · {agent.get('role') or 'Agent'}  —  "
            f"{agent.get('description') or 'No description configured.'}\n"
            f"Focus: {agent.get('scope') or 'Not assigned'}"
        )
        status = str(agent.get("status") or "")
        toggle = self.query_one("#operations-team-toggle", Button)
        toggle.disabled = status in {"archived", ""}
        toggle.label = "Disable selected" if status == "enabled" else "Enable selected"

    @on(Button.Pressed, "#operations-team-add")
    def handle_add_agent(self, _: Button.Pressed) -> None:
        self.app.push_screen(OperationsAgentDialog(), self._finish_add_agent)

    def _finish_add_agent(self, values: dict[str, str] | None) -> None:
        if values is None:
            return
        result = save_operations_agent(getattr(self.app, "workspace", None), **values)
        self.app.notify(result.message, severity="error" if not result.success else "information")
        if result.success:
            self._load_agent_roster()

    @on(DataTable.RowSelected, "#operations-team-roster")
    def handle_agent_selected(self, event: DataTable.RowSelected) -> None:
        agent_id = str(event.row_key.value)
        agent = next(
            (item for item in self._agent_rows if item.get("id") == agent_id), None
        )
        if agent is not None:
            self._select_agent(agent)

    @on(Button.Pressed, "#operations-team-toggle")
    def handle_toggle_agent(self, _: Button.Pressed) -> None:
        table = self.query_one("#operations-team-roster", DataTable)
        if table.cursor_row is None or not (0 <= table.cursor_row < len(self._agent_rows)):
            self.app.notify("Select a team member first.", severity="warning")
            return
        agent = self._agent_rows[table.cursor_row]
        result = set_operations_agent_status(
            getattr(self.app, "workspace", None),
            agent_id=str(agent.get("id") or ""),
            enabled=agent.get("status") != "enabled",
        )
        self.app.notify(result.message, severity="error" if not result.success else "information")
        if result.success:
            self._load_agent_roster()

    @on(Button.Pressed, "#operations-team-archive")
    def handle_archive_agent(self, _: Button.Pressed) -> None:
        table = self.query_one("#operations-team-roster", DataTable)
        if table.cursor_row is None or table.cursor_row < 0 or table.cursor_row >= len(self._agent_rows):
            self.app.notify("Select a team member first.", severity="warning")
            return
        agent = self._agent_rows[table.cursor_row]
        result = archive_operations_agent(
            getattr(self.app, "workspace", None), agent_id=str(agent.get("id") or "")
        )
        self.app.notify(result.message, severity="error" if not result.success else "information")
        if result.success:
            self._load_agent_roster()

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
        self._postmortem_saved_for.clear()
        self._observer_completed_for.clear()
        self._latest_recommendation = None
        self._observer_runs.clear()
        self._observer_status = "Standing by for a pipeline anomaly."
        self.query_one("#operations-get-details", Button).disabled = True
        self.query_one("#operations-monitor", Select).disabled = False
        self._show_snapshot(self._empty_snapshot())
        self._show_observer_state()
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

    @on(Select.Changed, "#operations-metric-view")
    def handle_metric_view_changed(self, event: Select.Changed) -> None:
        self._metric_view = str(event.value)
        pipeline = self._selected_pipeline()
        if pipeline is not None:
            self._populate_pipeline(pipeline.get("steps") or [])

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
            f"Acknowledged the incident for {pipeline.get('pipeline_name', 'workload')}.",
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
        self._launch_pipeline_observer(pipeline, automatic=False)

    def _launch_pipeline_observer(
        self, pipeline: dict[str, Any], *, automatic: bool
    ) -> None:
        """Record an anomaly first, then optionally ask the configured advisor."""

        pipeline_id = str(pipeline.get("id") or "")
        observer = next(
            (agent for agent in self._agent_rows if agent.get("id") == "pipeline-observer"),
            {},
        )
        if observer.get("status") == "disabled":
            if not automatic:
                self.app.notify("Pipeline Observer is disabled.", severity="warning")
            return
        if automatic and (not pipeline_id or pipeline_id in self._observer_completed_for):
            return
        if pipeline_id:
            self._observer_completed_for.add(pipeline_id)
        self.query_one("#operations-recommend-action", Button).disabled = True
        culprit = str(pipeline.get("culprit") or "the anomalous pipeline step")
        self._observer_status = f"Investigating {culprit}."
        self._show_observer_state(pipeline)
        self.app.notify(f"Pipeline Observer is investigating {culprit}.")
        self._record_activity(
            "observer_investigation_started",
            f"Pipeline Observer started investigating {culprit}.",
            actor="pipeline-observer",
            target=pipeline_id,
            status="investigating",
            details={"culprit": culprit, "automatic": automatic},
        )
        self._start_observer_run(pipeline, culprit)

        settings = load_operations_reasoning_settings(
            getattr(self.app, "workspace", None)
        )
        configured = bool(
            settings.success
            and (settings.data or {}).get("mode") != "disabled"
            and (settings.data or {}).get("endpoint")
            and (settings.data or {}).get("model")
        )
        if not configured:
            reason = (
                "The reasoning assistant is not configured."
                if settings.success
                else str(settings.message)
            )
            self._finish_observer_observation(pipeline, reason)
            return

        def reason() -> None:
            result = reason_about_operations_incident(
                getattr(self.app, "workspace", None), deepcopy(pipeline)
            )
            self.app.call_from_thread(
                self._finish_observer_investigation,
                deepcopy(pipeline),
                result,
                automatic,
            )

        self.app.run_worker(
            reason,
            thread=True,
            exclusive=True,
            group="operations-reasoning",
        )

    def _start_observer_run(self, pipeline: dict[str, Any], culprit: str) -> None:
        """Persist the agent's bounded investigation before reasoning starts."""

        workspace = getattr(self.app, "workspace", None)
        save_run = getattr(workspace, "save_operations_agent_run", None)
        record_message = getattr(workspace, "record_operations_agent_message", None)
        if not callable(save_run) or not callable(record_message):
            return
        pipeline_id = str(pipeline.get("id") or "")
        try:
            run = save_run(
                OperationsAgentRun(
                    agent_id="pipeline-observer",
                    pipeline_id=pipeline_id,
                    status="investigating",
                    summary=f"Investigate anomaly at {culprit}.",
                )
            )
            record_message(
                OperationsAgentMessage(
                    run_id=run.id,
                    author="pipeline-observer",
                    kind="observation",
                    content=f"Started investigation of anomalous step: {culprit}.",
                    details={"pipeline_id": pipeline_id, "culprit": culprit},
                )
            )
            if pipeline_id:
                self._observer_runs[pipeline_id] = run.id
        except Exception:
            # The live watcher still works for lightweight or pre-workspace hosts.
            return

    def _complete_observer_run(
        self, pipeline: dict[str, Any], *, status: str, content: str
    ) -> str:
        """Update the current run and append an immutable agent response."""

        pipeline_id = str(pipeline.get("id") or "")
        run_id = self._observer_runs.get(pipeline_id, "")
        if not run_id:
            return ""
        workspace = getattr(self.app, "workspace", None)
        save_run = getattr(workspace, "save_operations_agent_run", None)
        record_message = getattr(workspace, "record_operations_agent_message", None)
        if not callable(save_run) or not callable(record_message):
            return run_id
        try:
            save_run(
                OperationsAgentRun(
                    id=run_id,
                    agent_id="pipeline-observer",
                    pipeline_id=pipeline_id,
                    status=status,
                    summary=content,
                )
            )
            record_message(
                OperationsAgentMessage(
                    run_id=run_id,
                    author="pipeline-observer",
                    kind="proposal" if status == "proposal-ready" else "observation",
                    content=content,
                )
            )
        except Exception:
            pass
        return run_id

    def _finish_observer_investigation(
        self, pipeline: dict[str, Any], result, automatic: bool
    ) -> None:
        self.query_one("#operations-recommend-action", Button).disabled = False
        if result.success:
            payload = result.data or {}
            recommendation = str(payload.get("recommendation") or "")
            headline = str(payload.get("headline") or "Recommended remediation")
            verification = str(payload.get("verification") or "")
            actions = list(payload.get("actions") or [])
            actor = "reasoning-assistant"
            status = (
                "approval-required"
                if payload.get("mode") == "approval"
                else "advisory"
            )
            details = {"model": payload.get("model"), "execution": "manual"}
            proposal = {
                "pipeline": deepcopy(pipeline),
                "headline": headline,
                "description": recommendation,
                "verification": verification,
                "actions": actions,
                "mode": str(payload.get("mode") or "disabled"),
            }
            self._latest_recommendation = proposal
            run_id = self._complete_observer_run(
                pipeline, status="proposal-ready", content=f"Proposal: {headline}"
            )
            if not run_id:
                self._start_observer_run(
                    pipeline,
                    str(pipeline.get("culprit") or "the anomalous pipeline step"),
                )
                run_id = self._complete_observer_run(
                    pipeline, status="proposal-ready", content=f"Proposal: {headline}"
                )
            save_proposal = getattr(
                getattr(self.app, "workspace", None), "save_operations_agent_proposal", None
            )
            if run_id and callable(save_proposal):
                try:
                    save_proposal(
                        OperationsAgentProposal(
                            agent_id="pipeline-observer",
                            run_id=run_id,
                            pipeline_id=str(pipeline.get("id") or ""),
                            headline=headline,
                            description=recommendation,
                            verification=verification,
                            actions=actions,
                        )
                    )
                except Exception as exc:
                    self.app.notify(f"Could not save observer proposal: {exc}", severity="error")
                else:
                    self._refresh_agent_workspace("pipeline-observer")
            self._observer_status = f"Proposal ready: {headline}"
            self.query_one("#operations-remediation", Static).update(
                f"Proposal ready: {headline}"
            )
            self._show_observer_state(pipeline)
            self.app.notify(f"Pipeline Observer proposal ready: {headline}")
            self._record_activity(
                "remediation_proposed",
                headline,
                actor=actor,
                target=str(pipeline.get("id") or ""),
                status=status,
                details={
                    **details,
                    "description": recommendation,
                    "verification": verification,
                    "actions": actions,
                },
            )
            self._update_incident_actions(self._selected_pipeline())
            if not automatic:
                self._show_recommendation_dialog(proposal)
            return

        self._finish_observer_observation(pipeline, str(result.message))

    def _refresh_agent_workspace(self, agent_id: str) -> None:
        """Refresh the visible workspace when a selected agent gains new history."""

        workspace = self.query_one(OperationsAgentWorkspace)
        if workspace.agent and workspace.agent.get("id") == agent_id:
            workspace.show_agent(workspace.agent)

    def _finish_observer_observation(
        self, pipeline: dict[str, Any], reason: str
    ) -> None:
        """Record deterministic evidence without inventing a remediation."""

        culprit = str(pipeline.get("culprit") or "the anomalous pipeline step")
        quality_name = str(pipeline.get("quality_name") or "quality metric")
        quality_value = pipeline.get("quality_value")
        self.query_one("#operations-recommend-action", Button).disabled = False
        self._observer_status = "Evidence recorded; awaiting a configured reasoning assistant."
        self._complete_observer_run(
            pipeline,
            status="awaiting-reasoning",
            content=f"Evidence recorded; reasoning unavailable: {reason}",
        )
        self.query_one("#operations-remediation", Static).update(
            "Observer recorded an anomaly; no remediation was proposed."
        )
        self._show_observer_state(pipeline)
        self.app.notify("Pipeline Observer recorded evidence; reasoning is unavailable.")
        self._record_activity(
            "observer_observation",
            f"Detected {quality_name} anomaly at {culprit}"
            + (f" ({quality_value:.4f})." if isinstance(quality_value, (int, float)) else "."),
            actor="pipeline-observer",
            target=str(pipeline.get("id") or ""),
            status="awaiting-reasoning",
            details={
                "culprit": culprit,
                "quality_name": quality_name,
                "quality_value": quality_value,
                "reasoning_status": reason,
            },
        )
        self._update_incident_actions(self._selected_pipeline())

    def _show_recommendation_dialog(self, proposal: dict[str, Any]) -> None:
        self.app.push_screen(
            RecommendationDialog(
                headline=str(proposal["headline"]),
                description=str(proposal["description"]),
                verification=str(proposal["verification"]),
                actions=list(proposal["actions"]),
                mode=str(proposal["mode"]),
            ),
            lambda decision: self._handle_recommendation_decision(
                decision,
                pipeline=deepcopy(proposal["pipeline"]),
                headline=str(proposal["headline"]),
                description=str(proposal["description"]),
                actions=list(proposal["actions"]),
            ),
        )

    def _handle_recommendation_decision(
        self,
        decision: str | None,
        *,
        pipeline: dict[str, Any],
        headline: str,
        description: str,
        actions: list[dict[str, Any]],
    ) -> None:
        if decision == "plan":
            workspace = getattr(self.app, "workspace", None)
            result = add_operations_plan_item(
                workspace, headline=headline, description=description
            )
            if not result.success:
                self.app.notify(result.message, severity="error")
                return
            self._record_activity(
                "remediation_added_to_plan",
                headline,
                actor="user",
                target=str(pipeline.get("id") or ""),
                status="planned",
                details={"actions": actions},
            )
            self._load_plan()
            self.app.notify(result.message)
        elif decision == "execute":
            self._execute_recommendation(pipeline, headline, actions)

    def _execute_recommendation(
        self,
        pipeline: dict[str, Any],
        headline: str,
        actions: list[dict[str, Any]],
    ) -> None:
        self.app.notify("Executing approved MLOX remediation action…")

        def execute() -> None:
            result = execute_operations_remediation(
                getattr(self.app, "workspace", None),
                deepcopy(actions),
                pipeline=deepcopy(pipeline),
            )
            self.app.call_from_thread(
                self._finish_recommendation_execution,
                deepcopy(pipeline),
                headline,
                deepcopy(actions),
                result,
            )

        self.app.run_worker(
            execute,
            thread=True,
            exclusive=True,
            group="operations-remediation",
        )

    def _finish_recommendation_execution(
        self, pipeline, headline: str, actions: list[dict[str, Any]], result
    ) -> None:
        if not result.success:
            self._record_activity(
                "remediation_failed",
                headline,
                actor="user",
                target=str(pipeline.get("id") or ""),
                status="failed",
                details={"actions": actions, "error": result.message},
            )
            self.app.notify(result.message, severity="error")
            return
        self._record_activity(
            "remediation_executed",
            headline,
            actor="user",
            target=str(pipeline.get("id") or ""),
            status="executed",
            details={"actions": actions},
        )
        self.app.notify(result.message)

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
        self._postmortem_saved_for.add(str(pipeline.get("id") or ""))
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
        self.query_one("#operations-plan-board", OperationsPlanBoard).show_entry(board)
        self.query_one("#operations-plan-status", Static).update(result.message)
        self.query_one("#operations-plan-create", Button).display = board is None

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
        provider = self.query_one("#operations-reasoning-provider", Select).value
        result = save_operations_reasoning_settings(
            workspace,
            mode="advisory",
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
            "Pipeline Observer reasoning settings updated.",
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
                    "pipeline_name": snapshot.get("pipeline_name") or "observed workload",
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
            has_pipeline
            and state == "recovered"
            and str((pipeline or {}).get("id") or "") not in self._postmortem_saved_for
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
            name = str(pipeline.get("pipeline_name") or "observed workload")
            if state == "incident":
                self._postmortem_saved_for.discard(pipeline_id)
                culprit = str(pipeline.get("culprit") or "unknown origin")
                self._record_activity(
                    "incident_detected",
                    f"Detected an anomaly in {name}; likely origin: {culprit}.",
                    target=pipeline_id,
                    status="open",
                    details={"culprit": culprit},
                )
                self._launch_pipeline_observer(deepcopy(pipeline), automatic=True)
            elif state == "recovered":
                self._observer_completed_for.discard(pipeline_id)
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
                f"{pipeline.get('subject_name', pipeline.get('model_name', '-'))} / "
                f"{pipeline.get('subject_version', pipeline.get('model_version', '-'))}",
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
            if self._metric_view == "duration":
                eligible = [
                    item
                    for item in observations
                    if item.get("name") == "execution.duration_ms"
                ]
            else:
                eligible = [
                    item
                    for item in observations
                    if item.get("name") != "execution.duration_ms"
                ]
            focus = next(
                (item for item in eligible if item.get("anomalous")),
                eligible[0] if eligible else None,
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
            message = "Baseline complete. Watching new workload runs for deviations."
        else:
            message = "Start watching, then send healthy workload runs to establish a baseline."
        self.query_one("#operations-evidence", Static).update(message)
