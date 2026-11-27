"""Process-owned service tunnel controls."""

from __future__ import annotations

import asyncio
from textual import on
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Button, DataTable, Select, Static

from mlox.application.tunnels import TunnelManager
from mlox.service import ServiceCapability


class TunnelsPanel(Vertical):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.manager = None
        self._services = {}
        self._server_names = {}
        self._rows = []
        self._busy = False
        self._snapshot = None
        self._health = {}
        self._health_in_progress = set()
        self._table_timer = None
        self._health_timer = None

    def compose(self) -> ComposeResult:
        yield Static("Tunnels listen on this computer only and close when MLOX exits.", markup=False)
        yield Static("HTTPS certificates may require the original server hostname.", markup=False)
        with Horizontal(classes="tunnel-controls"):
            yield Select([], prompt="Choose service", id="tunnel-service")
            yield Select([("15 minutes", "900"), ("1 hour", "3600"), ("Until closed", "0")], value="3600", allow_blank=False, id="tunnel-duration")
            yield Button("Open", id="tunnel-open", variant="success")
            yield Button("Close selected", id="tunnel-close", variant="error")
        table = DataTable(id="tunnel-table", cursor_type="row")
        table.add_columns("Service", "Endpoint", "Remote server:port", "Local address", "Service health", "Expires")
        yield table
        yield Static("", id="tunnel-status", markup=False)

    def on_mount(self) -> None:
        workspace = getattr(self.app, "workspace", None)
        infra = getattr(workspace, "infrastructure", None)
        if infra is None:
            return
        self.manager = TunnelManager(getattr(infra, "get_server_by_uuid", lambda _: None))
        options = []
        for bundle in getattr(infra, "bundles", ()):
            server = getattr(bundle, "server", None)
            if server is not None:
                server_uuid = getattr(server, "uuid", None)
                server_key = server_uuid or getattr(server, "ip", None) or getattr(bundle, "name", "")
                self._server_names[str(server_key)] = str(getattr(bundle, "name", getattr(server, "ip", "")))
            for service in getattr(bundle, "services", ()):
                service_uuid = getattr(service, "uuid", None)
                # A tunnel needs stable server and service identifiers. Incomplete
                # in-memory objects are common in tests and imported workspaces;
                # leave those out of discovery instead of preventing the TUI from
                # mounting.
                if service_uuid and ServiceCapability.TUNNEL in getattr(service, "capabilities", set()):
                    service_id = str(service_uuid)
                    self._services[service_id] = service
                    options.append((f"{getattr(bundle, 'name', '')} / {getattr(service, 'name', service_id)}", service_id))
        self.query_one("#tunnel-service", Select).set_options(options)
        if options:
            self._table_timer = self.set_interval(1, self._refresh_table)
            self._health_timer = self.set_interval(30, self._refresh_health)

    def on_unmount(self) -> None:
        for timer in (self._table_timer, self._health_timer):
            if timer is not None:
                timer.stop()
        if self.manager is not None:
            self.manager.shutdown()

    def _refresh_table(self) -> None:
        if self.manager is None:
            return
        groups = self.manager.list_groups()
        snapshot = tuple((group.id, group.expires_at, group.bindings, self._health.get(group.id)) for group in groups)
        if snapshot == self._snapshot:
            return
        self._snapshot = snapshot
        table = self.query_one("#tunnel-table", DataTable)
        old_cursor = table.cursor_row
        table.clear()
        self._rows = []
        for group in groups:
            service = self._services.get(group.service_uuid)
            expires = group.expires_at.astimezone().strftime("%H:%M:%S") if group.expires_at else "Until closed"
            for binding in group.bindings:
                self._rows.append(group.id)
                scheme = "https://" if binding.endpoint.protocol == "https" else ""
                server = self._server_names.get(binding.endpoint.server_uuid, binding.endpoint.server_uuid)
                table.add_row(getattr(service, "name", group.service_uuid), binding.endpoint.name,
                              f"{server}:{binding.endpoint.remote_port}",
                              f"{scheme}{binding.local_host}:{binding.local_port}", self._health.get(group.id, "Not supported"), expires)
        if self._rows:
            table.move_cursor(row=min(old_cursor, len(self._rows) - 1))

    def _refresh_health(self) -> None:
        if self.manager is None:
            return
        groups = self.manager.list_groups()
        active_ids = {group.id for group in groups}
        self._health = {group_id: value for group_id, value in self._health.items() if group_id in active_ids}
        for group in groups:
            self._schedule_health(group)

    def _schedule_health(self, group) -> None:
        service = self._services.get(group.service_uuid)
        if (group.id in self._health_in_progress or service is None
                or ServiceCapability.HEALTH not in getattr(service, "capabilities", set())
                or not callable(getattr(service, "tunnel_health", None))):
            return
        self._health_in_progress.add(group.id)
        self._health[group.id] = "Checking…"
        asyncio.create_task(self._check_health(group, service))

    async def _check_health(self, group, service) -> None:
        try:
            health = await asyncio.to_thread(service.tunnel_health, self.app.workspace.infrastructure, group.bindings)
            if health is None:
                status = "Not supported"
            elif health.get("healthy") is True:
                status = "Healthy"
            elif health.get("healthy") is False and health.get("status") not in (None, "unknown"):
                status = "Unhealthy"
            else:
                status = "Unknown"
        except Exception:
            status = "Unknown"
        finally:
            self._health_in_progress.discard(group.id)
        if self.is_mounted and self.manager is not None and any(item.id == group.id for item in self.manager.list_groups()):
            self._health[group.id] = status
            self._refresh_table()

    @on(Button.Pressed, "#tunnel-open")
    async def open_selected(self) -> None:
        if self._busy or self.manager is None:
            return
        selected = self.query_one("#tunnel-service", Select).value
        service = self._services.get(str(selected))
        if service is None:
            self.query_one("#tunnel-status", Static).update("Select a service first.")
            return
        duration = int(self.query_one("#tunnel-duration", Select).value)
        infra = self.app.workspace.infrastructure
        self._busy = True
        self.query_one("#tunnel-status", Static).update("Opening tunnel…")
        try:
            plan = service.tunnel_plan(infra)
            group = await asyncio.to_thread(self.manager.open, plan, lambda bindings: service.tunnel_secrets(infra, bindings), duration=duration or None)
            self._schedule_health(group)
            self.query_one("#tunnel-status", Static).update("Tunnel opened. Connection credentials remain in memory.")
            self._refresh_table()
        except Exception as exc:
            self.query_one("#tunnel-status", Static).update(f"Could not open tunnel: {exc}")
        finally:
            self._busy = False

    @on(Button.Pressed, "#tunnel-close")
    async def close_selected(self) -> None:
        if self.manager is None or self._busy:
            return
        row = self.query_one("#tunnel-table", DataTable).cursor_row
        if row >= len(self._rows):
            return
        self._busy = True
        try:
            await asyncio.to_thread(self.manager.close, self._rows[row])
            self.query_one("#tunnel-status", Static).update("Tunnel closed.")
            self._refresh_table()
        except Exception as exc:
            self.query_one("#tunnel-status", Static).update(f"Could not close tunnel: {exc}")
        finally:
            self._busy = False
