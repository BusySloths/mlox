"""Project firewall management panel."""

from __future__ import annotations

from typing import Any, Optional
from datetime import datetime, timezone
from threading import Lock

from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from textual import on
from textual.app import ComposeResult
from textual.containers import Container, Horizontal, Vertical, VerticalScroll
from textual.reactive import reactive
from textual.screen import ModalScreen
from textual.widgets import Button, DataTable, Input, Label, Select, Static

from mlox.firewall import normalize_source

from mlox.application.use_cases.firewall import (
    describe_project_firewalls,
    describe_bundle_firewall,
    disable_bundle_firewall,
    preview_firewall_policy,
    apply_firewall_draft,
    persist_firewall_draft,
)

from .model import SelectionInfo


class FirewallDraftDialog(ModalScreen[tuple[str, list[str]] | None]):
    """Review and edit one server's policy before saving or applying it."""

    def __init__(self, data: dict[str, Any]) -> None:
        super().__init__()
        self.data = data
        self.sources = set(data["trusted_sources"])
        self.entries: list[tuple[str, str]] = []

    def compose(self) -> ComposeResult:
        with Container(id="firewall-draft-dialog"):
            yield Label(f"Firewall draft: {self.data['bundle']}", id="enable-firewall-title")
            yield Static("Select an address to change trust; public TCP ports are fixed.", markup=False)
            table = DataTable(id="firewall-draft-table")
            table.cursor_type = "row"
            table.add_columns("Policy", "Address / port", "Access")
            yield table
            with Horizontal(id="firewall-source-add"):
                yield Input(placeholder="IP address or CIDR", id="firewall-draft-source")
                yield Button("Add IP", id="add-firewall-draft", variant="success")
            yield Static("Suggestions are unverified. Apply is temporary; reboot may restore a saved policy.", id="firewall-draft-note", markup=False)
            yield Static("", id="firewall-draft-error", markup=False)
            with Horizontal(id="firewall-draft-actions"):
                yield Button("Toggle Trust", id="toggle-firewall-source")
                yield Button("Cancel", id="cancel-firewall-draft")
                yield Button("Save Draft", id="save-firewall-draft", variant="success")
                yield Button("Apply Draft", id="apply-firewall-draft", variant="warning")

    def on_mount(self) -> None:
        self._populate()

    def _populate(self) -> None:
        table = self.query_one("#firewall-draft-table", DataTable)
        table.clear()
        self.entries = []
        for port in self.data["public_tcp_ports"]:
            self.entries.append(("port", str(port)))
            table.add_row("Public TCP", str(port), "Everyone")
        for source in sorted(self.sources):
            self.entries.append(("trusted", source))
            table.add_row("Trusted source", source, "All ports")
        for peer in self.data["suggested_project_sources"]:
            address = peer["address"]
            if address not in self.sources:
                self.entries.append(("suggested", address))
                table.add_row(f"Suggested: {peer['bundle']}", address, "Unverified")
        for rule in self.data["fixed_rules"]:
            self.entries.append(("info", rule["description"]))
            table.add_row(rule["name"], rule["description"], rule["access"])

    @on(Button.Pressed)
    def handle_button(self, event: Button.Pressed) -> None:
        action = event.button.id
        error = self.query_one("#firewall-draft-error", Static)
        if action == "cancel-firewall-draft":
            self.dismiss(None)
        elif action == "add-firewall-draft":
            input_widget = self.query_one("#firewall-draft-source", Input)
            try:
                source = normalize_source(input_widget.value)
            except ValueError as exc:
                error.update(f"Invalid source: {exc}")
                return
            self.sources.add(source)
            input_widget.value = ""
            error.update("")
            self._populate()
        elif action == "toggle-firewall-source":
            index = self.query_one("#firewall-draft-table", DataTable).cursor_row
            if index >= len(self.entries):
                return
            kind, value = self.entries[index]
            if kind in ("port", "info"):
                error.update("This server-provided rule cannot be changed here.")
                return
            if kind == "trusted":
                self.sources.remove(value)
            else:
                self.sources.add(normalize_source(value))
            error.update("")
            self._populate()
        elif action in ("save-firewall-draft", "apply-firewall-draft"):
            if self.query_one("#firewall-draft-source", Input).value.strip():
                error.update("Add the entered IP first or clear the field.")
                return
            self.dismiss(("apply" if action == "apply-firewall-draft" else "save", sorted(self.sources)))


class PersistFirewallDialog(ModalScreen[bool]):
    def __init__(self, name: str) -> None:
        super().__init__()
        self.server_name = name

    def compose(self) -> ComposeResult:
        with Container(id="enable-firewall-dialog"):
            yield Label(f"Make policy permanent: {self.server_name}", id="enable-firewall-title")
            yield Static(
                "The applied policy must match the saved draft. It will be restored on reboot; "
                "rebooting will no longer remove this policy. On Docker servers restoration "
                "runs after Docker starts.", markup=False,
            )
            with Horizontal(id="enable-firewall-dialog-actions"):
                yield Button("Cancel", id="cancel-firewall-persist", classes="firewall-draft-button")
                yield Button("Make Permanent", id="confirm-firewall-persist", classes="firewall-draft-button", variant="warning")

    @on(Button.Pressed, "#cancel-firewall-persist")
    def cancel(self, _: Button.Pressed) -> None:
        self.dismiss(False)

    @on(Button.Pressed, "#confirm-firewall-persist")
    def confirm(self, _: Button.Pressed) -> None:
        self.dismiss(True)


class FirewallPanel(Static):
    """Project-level firewall inventory and bundle firewall controls."""

    selection: reactive[Optional[SelectionInfo]] = reactive(None)

    def __init__(self, *children, **kwargs) -> None:
        super().__init__(*children, **kwargs)
        self._rows: list[dict[str, Any]] = []
        self._row_ids: list[str] = []
        self._selected_id = ""
        self._loading = False
        self._access_lock = Lock()
        self._hold_timer = None
        self._hold_workspace = None
        self._access_generation = 0

    def compose(self) -> ComposeResult:
        with Vertical(id="firewall-content"):
            yield Static(id="firewall-summary", markup=False)
            with Horizontal(id="firewall-actions"):
                yield Button("Refresh", id="refresh-firewalls", variant="primary")
                yield Button("Edit and apply rules", id="edit-firewall-draft", variant="success")
                yield Button("Persist rules for reboots", id="persist-firewall", variant="warning", tooltip="Save the applied policy for reboot")
                yield Button("Disable", id="disable-firewall", variant="error")
            with Horizontal(id="firewall-access-actions"):
                yield Label("This computer:")
                yield Select([("15 minutes", "15m"), ("1 hour", "1h"), ("Hold while open", "hold")], value="15m", allow_blank=False, id="firewall-access-duration")
                yield Button("Add to all", id="firewall-access-add", variant="success")
                yield Button("Remove from all", id="firewall-access-remove", variant="warning")
            with Horizontal(id="firewall-browser"):
                table = DataTable(id="firewall-table")
                table.cursor_type = "row"
                table.add_columns(
                    "Server", "Firewall", "On reboot", "Temporary access",
                )
                yield table
                with VerticalScroll(id="firewall-detail-pane"):
                    yield Static("Select a server to manage its policy.", id="firewall-selected-server")
                    yield Static(id="firewall-detail", markup=False)

    @property
    def table(self) -> DataTable:
        return self.query_one("#firewall-table", DataTable)

    @property
    def summary(self) -> Static:
        return self.query_one("#firewall-summary", Static)

    @property
    def detail(self) -> Static:
        return self.query_one("#firewall-detail", Static)

    def on_mount(self) -> None:
        self.watch_selection(self.selection)
        self.set_interval(30, self._refresh_expiry_display)

    def _refresh_expiry_display(self) -> None:
        if self.display and self._rows:
            self._populate_table()
            if self._selected_id:
                self._select_row(self._selected_id)

    def _stop_access_hold(self) -> None:
        self._access_generation += 1
        self._hold_workspace = None
        if self._hold_timer is not None:
            self._hold_timer.stop()
            self._hold_timer = None

    @on(Button.Pressed, "#firewall-access-add")
    def add_this_computer(self) -> None:
        duration = self.query_one("#firewall-access-duration", Select).value
        self._stop_access_hold()
        self._run_access_action(str(duration))

    @on(Button.Pressed, "#firewall-access-remove")
    def remove_this_computer(self) -> None:
        self._stop_access_hold()
        self._run_access_action(None)

    def _run_access_action(self, duration: str | None, *, renewal: bool = False) -> None:
        from mlox.application.firewall_client import firewall_client_id
        from mlox.application.use_cases.firewall_grants import grant_current_computer, remove_computer_grant

        workspace = getattr(self.app, "workspace", None)
        infra = getattr(workspace, "infrastructure", None)
        generation = self._access_generation
        if not renewal:
            self._set_loading(True)

        def run() -> None:
            with self._access_lock:
                if renewal and generation != self._access_generation:
                    return
                try:
                    ident = firewall_client_id()
                    if duration is None:
                        result = remove_computer_grant(infra, grant_id=ident)
                    else:
                        seconds = {"15m": 900, "1h": 3600, "hold": 300}[duration]
                        result = grant_current_computer(infra, grant_id=ident, duration_seconds=seconds)
                except Exception as exc:
                    from mlox.application.result import OperationResult
                    result = OperationResult(False, 1, str(exc))
                self.app.call_from_thread(self._finish_access_action, result, duration, renewal, workspace)

        self.app.run_worker(run, thread=True, group="firewall-access")

    def _finish_access_action(self, result, duration: str | None, renewal: bool, workspace=None) -> None:
        if not renewal:
            self._set_loading(False)
        if workspace is not None and workspace is not getattr(self.app, "workspace", None):
            return
        data = result.data or {}
        ident = data.get("grant_id")
        for change in data.get("servers", []):
            row = next((row for row in self._rows if row.get("bundle") == change.get("server")), None)
            if row is None or row.get("temporary_grants") is None:
                continue
            if change["status"] in ("added", "removed"):
                grants = [grant for grant in row["temporary_grants"] if grant.get("grant_id") != ident]
                if change["status"] == "added":
                    grants.append({"grant_id": ident, "address": change["address"], "expires_at": change["expires_at"]})
                row["temporary_grants"] = grants
        self._populate_table()
        if self._selected_id:
            self._select_row(self._selected_id)
        failures = [f"{row['server']}: {row.get('message', 'failed')}" for row in data.get("servers", []) if row["status"] == "failed"]
        if not renewal or failures:
            self.notify(result.message + (" " + "; ".join(failures) if failures else ""), severity="information" if result.success else "error")
        if duration == "hold" and not renewal and any(row["status"] == "added" for row in data.get("servers", [])):
            self._hold_workspace = getattr(self.app, "workspace", None)
            self._hold_timer = self.set_interval(120, self._renew_access_hold)

    def _renew_access_hold(self) -> None:
        if getattr(self.app, "workspace", None) is not self._hold_workspace:
            self._stop_access_hold()
            return
        self._run_access_action("hold", renewal=True)

    def watch_selection(self, selection: Optional[SelectionInfo]) -> None:
        if not self.is_mounted:
            return
        if not selection or selection.type != "root":
            self.display = False
            return
        self.display = True
        self.load()

    def load(self) -> None:
        workspace = getattr(self.app, "workspace", None)
        infra = getattr(workspace, "infrastructure", None)
        self._set_loading(True)
        self.summary.update(Panel(Text("Loading firewall status..."), title="Firewall"))
        self.detail.update(self._help_panel())

        def load_firewalls() -> None:
            result = describe_project_firewalls(infra)
            self.app.call_from_thread(self._show_result, result)

        self.app.run_worker(
            load_firewalls,
            thread=True,
            exclusive=True,
            group="firewall-status",
        )

    def _show_result(self, result) -> None:
        self._set_loading(False)
        if not self.selection or self.selection.type != "root":
            return
        if not result.success:
            self.summary.update(
                Panel(Text(result.message, style="bold red"), title="Firewall")
            )
            return

        payload = result.data or {}
        previous_selection = self._selected_id
        self._rows = list(payload.get("rows", []))
        self._populate_table()
        self.summary.update(self._summary_panel(payload.get("summary", {})))
        if self._row_ids:
            self._select_row(previous_selection if previous_selection in self._row_ids else self._row_ids[0])
        else:
            self.detail.update(
                Panel(
                    Text("No firewall-capable servers detected.", style="dim"),
                    title="Firewall",
                    border_style="yellow",
                )
            )
        self._update_action_state()

    def _populate_table(self) -> None:
        table = self.table
        table.clear(columns=False)
        self._row_ids = []
        for row in self._rows:
            row_id = str(row.get("id") or row.get("bundle") or "")
            if not row_id:
                continue
            self._row_ids.append(row_id)
            table.add_row(
                str(row.get("bundle", "-")),
                self._firewall_badge(row),
                ("Saved" if row.get("persistence") == "enabled" else
                 "Not saved" if row.get("is_active") and row.get("persistence") == "disabled" else
                 "Off" if not row.get("is_active") and not row.get("status_error") and row.get("persistence") == "disabled" else "Unknown"),
                self._temporary_access_summary(row),
                key=row_id,
            )
        if self._row_ids:
            index = self._row_ids.index(self._selected_id) if self._selected_id in self._row_ids else 0
            table.cursor_coordinate = (index, 0)

    @staticmethod
    def _temporary_access_summary(row: dict[str, Any]) -> str:
        grants = row.get("temporary_grants")
        if grants is None:
            return "Unavailable"
        if not grants:
            return "None"
        try:
            expiries = [datetime.fromisoformat(str(grant["expires_at"])) for grant in grants]
            if any(expiry.tzinfo is None or expiry.utcoffset() is None for expiry in expiries):
                raise ValueError("Missing timezone")
            expiries = [expiry for expiry in expiries if expiry.astimezone(timezone.utc) > datetime.now(timezone.utc)]
            if not expiries:
                return "None"
            next_expiry = min(expiries, key=lambda expiry: expiry.astimezone(timezone.utc))
            return f"{len(expiries)} · {next_expiry.astimezone().strftime('%d %b %H:%M')}"
        except (KeyError, ValueError, TypeError):
            return f"{len(grants)} · expiry unknown"

    @on(DataTable.RowSelected, "#firewall-table")
    def handle_row_selected(self, event: DataTable.RowSelected) -> None:
        row_key = getattr(event.row_key, "value", event.row_key)
        self._select_row(str(row_key))

    @on(Button.Pressed, "#refresh-firewalls")
    def handle_refresh(self, _: Button.Pressed) -> None:
        self.load()

    @on(Button.Pressed, "#edit-firewall-draft")
    def handle_edit_draft(self, _: Button.Pressed) -> None:
        row = self._selected_row()
        workspace = getattr(self.app, "workspace", None)
        if not row or workspace is None:
            self.notify("Select a firewall-capable bundle.", severity="warning")
            return
        preview = preview_firewall_policy(workspace.infrastructure, row["bundle_ref"])
        if not preview.success:
            self.notify(preview.message, severity="error")
            return

        def edit(result: tuple[str, list[str]] | None) -> None:
            if result is None:
                return
            action, sources = result
            def save_and_apply():
                saved = workspace.replace_firewall_draft_sources(ip=str(row["server"]), sources=sources)
                if not saved.success or action == "save":
                    return saved
                return apply_firewall_draft(row["bundle_ref"])
            self._run_bundle_action(save_and_apply, "firewall-draft", row,
                                    refresh_on_failure=action == "apply")

        self.app.push_screen(FirewallDraftDialog(preview.data), edit)

    @on(Button.Pressed, "#persist-firewall")
    def handle_persist(self, _: Button.Pressed) -> None:
        row = self._selected_row()
        if not row:
            self.notify("Select a firewall-capable bundle.", severity="warning")
            return
        def persist(confirmed: bool | None) -> None:
            if confirmed:
                self._run_bundle_action(lambda: persist_firewall_draft(row["bundle_ref"]),
                                        "firewall-persist", row)
        self.app.push_screen(PersistFirewallDialog(str(row["bundle"])), persist)

    @on(Button.Pressed, "#disable-firewall")
    def handle_disable(self, _: Button.Pressed) -> None:
        row = self._selected_row()
        if not row:
            self.notify("Select a firewall-capable bundle.", severity="warning")
            return
        self._run_bundle_action(
            lambda: disable_bundle_firewall(row["bundle_ref"]),
            "firewall-disable",
            row,
        )

    def _run_bundle_action(self, operation, group: str, row: dict[str, Any], *, refresh_on_failure: bool = True) -> None:
        self._set_loading(True)
        row_id = str(row["id"])

        def run() -> None:
            result = operation()
            # On failure a remote operation may have partially changed the rules.
            refreshed = None
            if not result.success and refresh_on_failure:
                refreshed = describe_bundle_firewall(row["bundle_ref"])
            self.app.call_from_thread(self._finish_bundle_action, result, row_id, refreshed)

        self.app.run_worker(run, thread=True, exclusive=True, group=group)

    def _finish_bundle_action(self, result, row_id: str, refreshed=None) -> None:
        self._set_loading(False)
        if not result.success:
            self.notify(result.message, severity="error")
        else:
            self.notify(result.message)
        status_result = refreshed if refreshed is not None else result
        updated = (status_result.data or {}).get("firewall")
        if updated is not None:
            for index, old_row in enumerate(self._rows):
                if str(old_row.get("id")) == row_id:
                    self._rows[index] = updated
                    break
        # A failed workspace mutation reloads the project graph; never retain stale
        # bundle objects for a subsequent action.
        workspace = getattr(self.app, "workspace", None)
        infra = getattr(workspace, "infrastructure", None)
        for item in self._rows:
            current = next((b for b in getattr(infra, "bundles", [])
                            if str(getattr(b.server, "uuid", "")) == str(item.get("id"))), None)
            if current is not None:
                item["bundle_ref"] = current
        if updated is not None:
            self._populate_table()
            active = sum(bool(item.get("is_active")) and not item.get("status_error") for item in self._rows)
            unknown = sum(bool(item.get("status_error")) for item in self._rows)
            self.summary.update(self._summary_panel({"capable": len(self._rows), "active": active,
                                                     "inactive": len(self._rows) - active - unknown, "unknown": unknown}))
        self._select_row(self._selected_id)

    def _select_row(self, row_id: str) -> None:
        self._selected_id = row_id
        row = self._selected_row()
        self.query_one("#firewall-selected-server", Static).update(
            f"Selected: {row['bundle']} ({row['server']})"
            if row else "Select a server to manage its policy draft."
        )
        self.detail.update(self._detail_panel(row) if row else self._help_panel())
        self._update_action_state()

    def _selected_row(self) -> dict[str, Any] | None:
        for row in self._rows:
            if str(row.get("id") or row.get("bundle") or "") == self._selected_id:
                return row
        return None

    def _summary_panel(self, summary: dict[str, Any]) -> Text:
        unknown = f"  ·  {summary['unknown']} unknown" if summary.get("unknown") else ""
        return Text(f"Firewall  ·  {summary.get('capable', 0)} servers  ·  "
                    f"{summary.get('active', 0)} active  ·  {summary.get('inactive', 0)} inactive{unknown}", style="bold")

    def _detail_panel(self, row: dict[str, Any]) -> Panel:
        workspace = getattr(self.app, "workspace", None)
        infra = getattr(workspace, "infrastructure", None)
        draft = preview_firewall_policy(infra, row["bundle_ref"]) if row.get("bundle_ref") else None
        layout = Table.grid(expand=True)
        layout.add_column(justify="right", style="cyan")
        layout.add_column(ratio=3)
        layout.add_row("MLOX LIVE", self._firewall_badge(row))
        layout.add_row("Address", str(row.get("server", "-")))
        persistence = {"enabled": "Saved for reboot (may differ from live)",
                       "disabled": "Not saved for reboot", "unknown": "Unknown"}
        layout.add_row("On reboot", persistence.get(row.get("persistence"), "Unknown"))
        if row.get("status_error"):
            layout.add_row("Public TCP", Text("unknown", style="yellow"))
        elif not row.get("is_active"):
            layout.add_row("Public TCP", "Not managed by MLOX")
        else:
            layout.add_row("Public TCP", self._ports_text(row.get("public_ports", []), row.get("open_ports_unknown")))
        if row.get("is_active") and not row.get("status_error"):
            trusted = "Per-port legacy rules" if row.get("legacy_policy") else ", ".join(row.get("trusted_sources", [])) or "none"
            layout.add_row("Trusted sources", trusted)
            grants = row.get("temporary_grants")
            if grants is None:
                layout.add_row("Temporary access", "Unavailable")
            elif self._temporary_access_summary(row) == "None":
                layout.add_row("Temporary access", "None")
            else:
                for grant in grants:
                    try:
                        expiry = datetime.fromisoformat(str(grant["expires_at"]))
                        if expiry.tzinfo is not None and expiry.astimezone(timezone.utc) <= datetime.now(timezone.utc):
                            continue
                    except (KeyError, ValueError, TypeError):
                        pass
                    layout.add_row("Temporary access", f"{grant.get('address', '?')} · {grant.get('expires_at', '?')}")
        if row.get("legacy_policy"):
            layout.add_row("Previous policy", "Older rules detected; apply the draft to replace them.")
        error = str(row.get("status_error") or "")
        if error:
            layout.add_row("Status Error", Text(error, style="bold red"))
        layout.add_row("", "")
        layout.add_row("DRAFT", "Saved in this project; not necessarily applied")
        if draft is not None and draft.success:
            layout.add_row("Public TCP", self._ports_text(draft.data["public_tcp_ports"]))
            layout.add_row("Trusted sources", ", ".join(draft.data["trusted_sources"]) or "none")
        elif draft is not None:
            layout.add_row("Draft error", Text(draft.message, style="bold red"))
        return Panel(
            layout,
            title=f"Policy: {row.get('bundle', '-')}",
            border_style="green" if row.get("is_active") else "yellow",
        )

    def _help_panel(self) -> Panel:
        return Panel(
            Text(
                "Select a firewall-capable bundle to inspect open ports. "
                "Review and edit its draft, apply it, then make it permanent if desired."
            ),
            title="Firewall",
            border_style="cyan",
        )

    def _firewall_badge(self, row: dict[str, Any]) -> Text:
        if row.get("status_error"):
            return Text(" Error ", style="bold white on dark_red")
        if row.get("is_active"):
            return Text(" Active ", style="bold white on dark_green")
        return Text(" Inactive ", style="bold black on bright_yellow")

    def _ports_text(self, ports: object, unknown: object = False) -> Text:
        if unknown:
            return Text("unknown", style="yellow")
        values = [str(port) for port in ports or []]
        if not values:
            return Text("none", style="dim")
        return Text(", ".join(values))

    def _set_loading(self, loading: bool) -> None:
        self._loading = loading
        self._update_action_state()

    def _update_action_state(self) -> None:
        if not self.is_mounted:
            return
        selected = self._selected_row()
        for button in self.query(Button):
            button.disabled = self._loading
        if selected is None:
            self.query_one("#edit-firewall-draft", Button).disabled = True
            self.query_one("#persist-firewall", Button).disabled = True
            self.query_one("#disable-firewall", Button).disabled = True
            return
        self.query_one("#disable-firewall", Button).disabled = (
            self._loading or (not bool(selected.get("is_active")) and selected.get("persistence") != "enabled")
        )
        self.query_one("#persist-firewall", Button).disabled = (
            self._loading or not bool(selected.get("is_active"))
        )
