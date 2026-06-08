"""Overview panel tests."""

from __future__ import annotations

from types import SimpleNamespace

from rich.console import Console

from mlox.tui.screens.dashboard.model import SelectionInfo
from mlox.tui.screens.dashboard.overview_panel import OverviewPanel


def test_bundle_overview_shows_backend() -> None:
    rendered = []
    panel = OverviewPanel()
    panel.update = rendered.append
    server = SimpleNamespace(
        ip="10.0.0.1",
        state="running",
        backend=["docker", "native"],
    )
    panel.show_bundle(
        SelectionInfo(
            type="bundle",
            bundle=SimpleNamespace(
                name="demo",
                tags=[],
                services=[],
                server=server,
            ),
            server=server,
        )
    )

    console = Console(record=True, width=100)
    console.print(rendered[0])
    overview = console.export_text()

    assert "Backend" in overview
    assert "docker, native" in overview
