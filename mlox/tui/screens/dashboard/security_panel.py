"""Project security workspace: firewall, tunnels, and an explicit bounded check."""

from __future__ import annotations

from typing import Optional

from textual import on
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.reactive import reactive
from textual.widgets import Button, DataTable, Select, Static, TabbedContent, TabPane

from mlox.application.use_cases.security import check_common_tcp_ports
from .firewall_panel import FirewallPanel
from .model import SelectionInfo
from .tunnels_panel import TunnelsPanel


class SecurityTestsPanel(Vertical):
    """User-triggered checks with a fixed, low-volume target and port list."""

    def compose(self) -> ComposeResult:
        yield Static(
            "One pass against nine common TCP ports on one selected project server. "
            "No port ranges, retries, or background scans.",
            id="security-test-note",
        )
        with Horizontal(id="security-test-controls"):
            yield Select([], prompt="Choose server", id="security-test-server")
            yield Button("Check common ports", id="security-test-run", variant="primary")
        table = DataTable(id="security-test-results", cursor_type="row")
        table.add_columns("Port", "Result", "Time")
        yield table
        yield Static("Select a server and run the check when needed.", id="security-test-status")

    def on_mount(self) -> None:
        workspace = getattr(self.app, "workspace", None)
        infra = getattr(workspace, "infrastructure", None)
        options = []
        self._servers = {}
        for bundle in getattr(infra, "bundles", ()):
            server = getattr(bundle, "server", None)
            if server is None:
                continue
            ident = str(getattr(server, "uuid", getattr(server, "ip", "")))
            self._servers[ident] = server
            options.append((f"{getattr(bundle, 'name', ident)} · {getattr(server, 'ip', '')}", ident))
        self.query_one("#security-test-server", Select).set_options(options)

    @on(Button.Pressed, "#security-test-run")
    def run_check(self, _: Button.Pressed) -> None:
        selected = self.query_one("#security-test-server", Select).value
        server = self._servers.get(str(selected))
        if server is None:
            self.query_one("#security-test-status", Static).update("Choose a project server first.")
            return
        button = self.query_one("#security-test-run", Button)
        button.disabled = True
        self.query_one("#security-test-status", Static).update("Checking…")

        def run() -> None:
            result = check_common_tcp_ports(server)
            self.app.call_from_thread(self._show_result, result)

        self.app.run_worker(run, thread=True, exclusive=True, group="security-check")

    def _show_result(self, result) -> None:
        self.query_one("#security-test-run", Button).disabled = False
        status = self.query_one("#security-test-status", Static)
        table = self.query_one("#security-test-results", DataTable)
        table.clear()
        if not result.success:
            status.update(result.message)
            return
        for row in result.data["ports"]:
            table.add_row(str(row["port"]), str(row["state"]), f"{row['milliseconds']} ms")
        status.update(result.message)


class SecurityPanel(Vertical):
    """Security workspace with the same hero, navigation, and stage layout as Operations."""

    selection: reactive[Optional[SelectionInfo]] = reactive(None)

    def compose(self) -> ComposeResult:
        with Horizontal(id="security-workspace"):
            with Vertical(id="security-nav"):
                yield Button("Firewall", id="security-nav-firewall", classes="security-nav-active")
                yield Button("Tunnels", id="security-nav-tunnels")
                yield Button("Port check", id="security-nav-tests")
                yield Static("Protect\nConnect\nCheck", id="security-nav-footer")
            with Vertical(id="security-stage"):
                with Vertical(id="security-hero"):
                    yield Static("PROJECT SECURITY", id="security-eyebrow")
                    yield Static("Firewall", id="security-title")
                    yield Static("Firewall policy, temporary access, and private service tunnels.", id="security-subtitle")
                with TabbedContent(id="security-sections"):
                    with TabPane("Firewall", id="security-firewall-section"):
                        yield FirewallPanel(id="firewall-panel")
                    with TabPane("Tunnels", id="security-tunnels-section"):
                        yield TunnelsPanel(id="tunnels-panel")
                    with TabPane("Port check", id="security-tests-section"):
                        yield SecurityTestsPanel(id="security-tests-panel")

    def on_mount(self) -> None:
        self._activate("firewall")
        self.watch_selection(self.selection)

    def watch_selection(self, selection: Optional[SelectionInfo]) -> None:
        if not self.is_mounted:
            return
        root = selection if selection and selection.type == "root" else None
        self.display = root is not None
        self.query_one(FirewallPanel).selection = root

    @on(Button.Pressed, "#security-nav-firewall")
    @on(Button.Pressed, "#security-nav-tunnels")
    @on(Button.Pressed, "#security-nav-tests")
    def navigate(self, event: Button.Pressed) -> None:
        self._activate(str(event.button.id).removeprefix("security-nav-"))

    def _activate(self, section: str) -> None:
        self.query_one("#security-sections", TabbedContent).active = f"security-{section}-section"
        titles = {
            "firewall": ("Firewall", "Control inbound access and temporary computer access."),
            "tunnels": ("Tunnels", "Reach selected services through local-only SSH tunnels."),
            "tests": ("Port check", "Check nine common TCP ports on one selected server."),
        }
        title, subtitle = titles[section]
        self.query_one("#security-title", Static).update(title)
        self.query_one("#security-subtitle", Static).update(subtitle)
        for name in titles:
            self.query_one(f"#security-nav-{name}", Button).set_class(name == section, "security-nav-active")
