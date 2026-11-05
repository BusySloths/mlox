"""Tests for the focused service log viewer."""

import asyncio
from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace

from textual.app import App, ComposeResult
from textual.widgets import Button

from mlox.tui.screens.dashboard.log_panel import LogPanel
from mlox.tui.screens.dashboard.model import SelectionInfo


class LogTestApp(App):
    CSS_PATH = Path(__file__).resolve().parents[3] / "mlox/tui/tui.tcss"

    def compose(self) -> ComposeResult:
        yield LogPanel(id="selection-logs")


def test_logs_have_room_and_ignore_late_results_after_source_change():
    async def exercise():
        app = LogTestApp()
        service = SimpleNamespace(
            compose_service_names={"App": "app", "Worker": "worker"},
            exec=SimpleNamespace(history=[]),
            capabilities={"logs"}, log_labels=lambda: ["App", "Worker"],
            log_tail=lambda conn, label, tail: "",
        )
        async with app.run_test(size=(80, 24)) as pilot:
            panel = app.query_one(LogPanel)
            panel.selection = SelectionInfo(type="service", service=service)
            await pilot.pause()
            assert panel.log_output.region.height >= 14
            source = panel.label_input.region
            lines = panel.tail_input.region
            fetch = panel.query_one("#log-fetch", Button).region
            assert source.y == lines.y == fetch.y
            assert source.height == lines.height == fetch.height == 3
            assert source.width <= 24
            assert lines.width >= 12
            old_generation = panel._request_generation
            panel.label_input.value = "Worker"
            await pilot.pause()
            panel._finish_fetch(old_generation, "old source", None)
            assert "old source" not in panel.log_output.lines
            panel._finish_fetch(panel._request_generation, "worker log", None)
            assert panel.log_output.lines == ["worker log"]

    asyncio.run(exercise())


def test_invalid_line_count_is_rejected():
    async def exercise():
        app = LogTestApp()
        service = SimpleNamespace(
            compose_service_names={"App": "app"}, exec=SimpleNamespace(history=[]),
            capabilities={"logs"}, log_labels=lambda: ["App"],
            log_tail=lambda conn, label, tail: "",
        )
        bundle = SimpleNamespace(server=object())
        async with app.run_test() as pilot:
            panel = app.query_one(LogPanel)
            panel.selection = SelectionInfo(type="service", service=service, bundle=bundle)
            await pilot.pause()
            panel.tail_input.value = "0"
            panel.query_one("#log-fetch", Button).press()
            await pilot.pause()
            assert "positive" in str(panel.status.render())
            assert not panel.query_one("#log-fetch", Button).disabled

    asyncio.run(exercise())


def test_log_toolbar_fits_a_narrow_panel():
    async def exercise():
        app = LogTestApp()
        async with app.run_test(size=(36, 24)) as pilot:
            await pilot.pause()
            controls = app.query_one("#log-controls")
            fetch = app.query_one("#log-fetch", Button)
            assert fetch.region.right <= controls.region.right
            assert fetch.region.height == 3

    asyncio.run(exercise())


def test_server_logs_are_available_in_the_same_view():
    async def exercise():
        app = LogTestApp()
        server = SimpleNamespace(
            capabilities={"logs"}, log_labels=lambda: ["System journal"],
            log_tail=lambda conn, label, tail: f"{label}: {tail}",
            get_server_connection=lambda: nullcontext(object()),
        )
        async with app.run_test(size=(80, 24)) as pilot:
            panel = app.query_one(LogPanel)
            panel.selection = SelectionInfo(type="server", server=server)
            await pilot.pause()
            assert panel.label_input.value == "System journal"
            panel.query_one("#log-fetch", Button).press()
            for _ in range(50):
                await pilot.pause(0.02)
                if panel.log_output.line_count:
                    break
            assert panel.log_output.lines == ["System journal: 200"]

    asyncio.run(exercise())
