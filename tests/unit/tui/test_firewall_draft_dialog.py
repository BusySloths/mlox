import asyncio
import io
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from rich.console import Console
from textual.app import App
from textual.widgets import DataTable, Input

from mlox.application.result import OperationResult
from mlox.server import ServerCapability
from mlox.firewall import FirewallPolicy
from mlox.tui.screens.dashboard.firewall_panel import FirewallDraftDialog, FirewallPanel, PersistFirewallDialog


class DraftTestApp(App):
    CSS_PATH = str(Path(__file__).resolve().parents[3] / "mlox/tui/tui.tcss")


def _draft_data():
    return {"bundle": "sartre", "public_tcp_ports": [22, 80, 443],
            "trusted_sources": ["192.0.2.4"],
            "fixed_rules": [],
            "suggested_project_sources": [{"bundle": "peer", "address": "203.0.113.5"}]}


def test_draft_dialog_stages_source_and_saves():
    asyncio.run(_check_draft_save())


async def _check_draft_save():
    app = DraftTestApp()
    received = []
    async with app.run_test(size=(100, 40)) as pilot:
        app.push_screen(FirewallDraftDialog(_draft_data()), received.append)
        await pilot.pause()
        app.screen.query_one("#firewall-draft-source", Input).value = "192.0.2.5"
        await pilot.click("#add-firewall-draft")
        await pilot.click("#save-firewall-draft")
        await pilot.pause()
    assert received == [("save", ["192.0.2.4", "192.0.2.5"])]


def test_draft_dialog_toggles_selected_sources_and_applies():
    asyncio.run(_check_draft_apply())


async def _check_draft_apply():
    app = DraftTestApp()
    received = []
    async with app.run_test(size=(100, 40)) as pilot:
        app.push_screen(FirewallDraftDialog(_draft_data()), received.append)
        await pilot.pause()
        table = app.screen.query_one("#firewall-draft-table", DataTable)
        table.move_cursor(row=3)
        await pilot.pause()
        await pilot.click("#toggle-firewall-source")
        assert app.screen.sources == set()
        assert app.screen.entries[3] == ("suggested", "203.0.113.5")
        await pilot.pause(0.3)
        table.move_cursor(row=3)
        await pilot.pause()
        assert table.cursor_row == 3
        await pilot.click("#toggle-firewall-source")
        await pilot.click("#apply-firewall-draft")
        await pilot.pause()
    assert received == [("apply", ["203.0.113.5"])]


def test_cancel_keeps_staged_changes_local():
    asyncio.run(_check_cancel())


async def _check_cancel():
    app = DraftTestApp()
    received = []
    async with app.run_test(size=(100, 40)) as pilot:
        app.push_screen(FirewallDraftDialog(_draft_data()), received.append)
        await pilot.pause()
        app.screen.query_one("#firewall-draft-source", Input).value = "192.0.2.5"
        await pilot.click("#add-firewall-draft")
        await pilot.click("#cancel-firewall-draft")
        await pilot.pause()
    assert received == [None]


def test_apply_saves_reviewed_sources_before_applying():
    asyncio.run(_check_save_then_apply())


async def _check_save_then_apply():
    class PanelApp(DraftTestApp):
        def compose(self):
            yield FirewallPanel()

    events = []
    server = SimpleNamespace(uuid="s1", ip="192.0.2.1", port=22, backend=["docker"],
                             capabilities={ServerCapability.FIREWALL},
                             firewall_default_policy=lambda: FirewallPolicy((22, 80, 443)),
                             firewall_validate_policy=lambda policy: None,
                             firewall_policy_rules=lambda: ())
    bundle = SimpleNamespace(name="sartre", server=server, services=[], firewall_policy_draft=None)
    def save(*, ip, sources):
        events.append(("save", ip, sources))
        return OperationResult(True, 0, "saved", {"applied": False})
    def apply(selected):
        events.append(("apply", selected.name))
        return OperationResult(True, 0, "applied", {"applied": True})
    app = PanelApp()
    app.workspace = SimpleNamespace(infrastructure=SimpleNamespace(bundles=[bundle]),
                                    replace_firewall_draft_sources=save)
    with patch("mlox.tui.screens.dashboard.firewall_panel.apply_firewall_draft", apply):
        async with app.run_test(size=(100, 40)) as pilot:
            panel = app.query_one(FirewallPanel)
            panel.display = True
            panel._rows = [{"id": "s1", "bundle": "sartre", "server": server.ip,
                            "bundle_ref": bundle, "is_active": False}]
            panel._populate_table()
            panel._select_row("s1")
            await pilot.pause()
            await pilot.click("#edit-firewall-draft")
            app.screen.query_one("#firewall-draft-source", Input).value = "192.0.2.5"
            await pilot.click("#add-firewall-draft")
            await pilot.click("#apply-firewall-draft")
            await pilot.pause(0.3)
    assert events == [("save", "192.0.2.1", ["192.0.2.5"]), ("apply", "sartre")]


def test_persist_dialog_requires_confirmation():
    asyncio.run(_check_persist_confirmation())


async def _check_persist_confirmation():
    app = App()
    received = []
    async with app.run_test(size=(100, 30)) as pilot:
        app.push_screen(PersistFirewallDialog("sartre"), received.append)
        await pilot.pause()
        await pilot.click("#confirm-firewall-persist")
        await pilot.pause()
    assert received == [True]


def test_draft_result_keeps_selected_server_and_does_not_reload_statuses():
    asyncio.run(_check_draft_result())


async def _check_draft_result():
    class PanelApp(App):
        def compose(self):
            yield FirewallPanel()

    app = PanelApp()
    server = SimpleNamespace(uuid="s2")
    bundle = SimpleNamespace(name="second", server=server)
    app.workspace = SimpleNamespace(infrastructure=SimpleNamespace(bundles=[bundle]))
    async with app.run_test() as pilot:
        panel = app.query_one(FirewallPanel)
        row = {"id": "s2", "bundle": "second", "server": "192.0.2.2", "bundle_ref": bundle}
        panel._rows = [row]
        panel._populate_table()
        panel._select_row("s2")
        def unexpected_load():
            raise AssertionError("draft changes must not reload remote statuses")
        panel.load = unexpected_load
        panel._finish_bundle_action(OperationResult(True, 0, "saved", {"applied": False}), "s2")
        await pilot.pause()
        assert panel._selected_id == "s2"
        assert panel._selected_row()["bundle_ref"] is bundle


def test_panel_shows_selected_server_live_and_draft_without_legacy_controls():
    asyncio.run(_check_policy_panel())


async def _check_policy_panel():
    class PanelApp(App):
        def compose(self):
            yield FirewallPanel()

    server = SimpleNamespace(uuid="s1", ip="192.0.2.1", port=22, backend=["docker"],
                             capabilities={ServerCapability.FIREWALL},
                             firewall_default_policy=lambda: FirewallPolicy((22, 80, 443)),
                             firewall_validate_policy=lambda policy: None,
                             firewall_policy_rules=lambda: ())
    bundle = SimpleNamespace(name="sartre", server=server, services=[],
                             firewall_policy_draft={"public_tcp_ports": [22, 80, 443],
                                                    "trusted_sources": ["192.0.2.7"]})
    app = PanelApp()
    app.workspace = SimpleNamespace(infrastructure=SimpleNamespace(bundles=[bundle]))
    async with app.run_test(size=(120, 40)) as pilot:
        panel = app.query_one(FirewallPanel)
        row = {"id": "s1", "bundle": "sartre", "server": server.ip, "bundle_ref": bundle,
               "is_active": True, "persistence": "enabled", "public_ports": [22, 443],
               "trusted_sources": ["192.0.2.8"], "raw_status": "Status: active"}
        panel._rows = [row]
        panel.display = True
        panel._populate_table()
        panel._select_row("s1")
        console = Console(file=io.StringIO(), record=True, width=100)
        console.print(panel._detail_panel(row))
        rendered = console.export_text()
        assert "MLOX LIVE" in rendered and "DRAFT" in rendered
        assert "192.0.2.8" in rendered and "192.0.2.7" in rendered
        assert not panel.query("#enable-firewall")
        assert not panel.query("#toggle-firewall-rules")
