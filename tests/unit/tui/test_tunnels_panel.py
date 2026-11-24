import asyncio
from contextlib import contextmanager
from threading import Event
from types import SimpleNamespace

from textual.app import App, ComposeResult
from textual.widgets import DataTable, Select, Static

from mlox.service import ServiceCapability
from mlox.server import ServerCapability
from mlox.tui.screens.dashboard.tunnels_panel import TunnelsPanel
from mlox.tunnel import TunnelBinding, TunnelEndpoint, TunnelPlan


def test_panel_opens_and_cleans_up_tunnel_without_displaying_secrets():
    asyncio.run(_check_panel())


async def _check_panel():
    closed = []
    endpoint = TunnelEndpoint("svc", "Web", "server", "127.0.0.1", 443, "https")

    class Server:
        capabilities = {ServerCapability.TUNNEL}
        @contextmanager
        def open_tunnel(self, item):
            try:
                yield TunnelBinding(item, 12345)
            finally:
                closed.append(True)

    service = SimpleNamespace(uuid="svc", name="Example", capabilities={ServiceCapability.TUNNEL, ServiceCapability.HEALTH},
                              tunnel_plan=lambda infra: TunnelPlan("svc", (endpoint,)),
                              tunnel_secrets=lambda infra, bindings: {"password": "hidden-password"},
                              tunnel_health=lambda infra, bindings: {"status": "running", "healthy": True})
    infra = SimpleNamespace(bundles=[SimpleNamespace(services=[service])], get_server_by_uuid=lambda _: Server())

    class TestApp(App):
        def __init__(self):
            super().__init__()
            self.workspace = SimpleNamespace(infrastructure=infra)

        def compose(self) -> ComposeResult:
            yield TunnelsPanel()

    app = TestApp()
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        app.query_one("#tunnel-service", Select).value = "svc"
        await pilot.click("#tunnel-open")
        await pilot.pause(0.2)
        table = app.query_one("#tunnel-table", DataTable)
        assert table.row_count == 1
        assert "127.0.0.1:12345" in str(table.get_row_at(0))
        assert "server:443" in str(table.get_row_at(0))
        assert "Healthy" in str(table.get_row_at(0))
        assert "hidden-password" not in str(app.query_one("#tunnel-status", Static).render())
    assert closed == [True]


def test_slow_health_check_does_not_block_panel():
    asyncio.run(_check_slow_health())


async def _check_slow_health():
    started, release = Event(), Event()
    endpoint = TunnelEndpoint("svc", "Web", "server", "127.0.0.1", 443, "https")

    class Server:
        capabilities = {ServerCapability.TUNNEL}
        @contextmanager
        def open_tunnel(self, item):
            yield TunnelBinding(item, 12345)

    def slow_health(infra, bindings):
        started.set()
        release.wait(3)
        return {"status": "running", "healthy": True}

    service = SimpleNamespace(uuid="svc", name="Example", capabilities={ServiceCapability.TUNNEL, ServiceCapability.HEALTH},
                              tunnel_plan=lambda infra: TunnelPlan("svc", (endpoint,)),
                              tunnel_secrets=lambda infra, bindings: {}, tunnel_health=slow_health)
    infra = SimpleNamespace(bundles=[SimpleNamespace(services=[service])], get_server_by_uuid=lambda _: Server())

    class TestApp(App):
        def __init__(self):
            super().__init__()
            self.workspace = SimpleNamespace(infrastructure=infra)
        def compose(self) -> ComposeResult:
            yield TunnelsPanel()

    app = TestApp()
    try:
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            app.query_one("#tunnel-service", Select).value = "svc"
            await pilot.click("#tunnel-open")
            await pilot.pause(0.1)
            assert started.is_set()
            assert "Checking" in str(app.query_one("#tunnel-table", DataTable).get_row_at(0))
            await pilot.click("#tunnel-close")
            await pilot.pause(0.1)
            assert app.query_one("#tunnel-table", DataTable).row_count == 0
    finally:
        release.set()
