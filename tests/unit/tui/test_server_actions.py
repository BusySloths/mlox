"""Server action widget tests."""

from __future__ import annotations

import asyncio
import io
import threading
from types import SimpleNamespace

from rich.console import Console
from textual.app import App, ComposeResult
from textual.widgets import Button, Static

from mlox.server import ServerCapability
from mlox.tui.screens.dashboard.model import SelectionInfo
from mlox.tui.screens.dashboard.screen import DashboardScreen
from mlox.tui.screens.dashboard.server_actions import ServerActions
from mlox.tui.screens.dashboard.server_info_panel import ServerInfoPanel


class ServerActionsTestApp(App):
    def compose(self) -> ComposeResult:
        yield ServerActions()


class DashboardServerInfoTestApp(App):
    def __init__(self) -> None:
        super().__init__()
        project = SimpleNamespace(
            name="test-project",
            infrastructure=SimpleNamespace(bundles=[]),
        )
        self.workspace = SimpleNamespace(
            name=project.name,
            infrastructure=project.infrastructure,
            path="test-project",
            active_secret_manager_name="Embedded Project Storage",
        )

    def compose(self) -> ComposeResult:
        yield DashboardScreen()


def _render_text(renderable: object) -> str:
    if isinstance(renderable, str):
        return renderable
    console = Console(file=io.StringIO(), record=True, width=140)
    console.print(renderable)
    return console.export_text()


def _render_server_info_panel(app: App) -> str:
    return _render_text(app.query_one(ServerInfoPanel).content)


def _terminal_server(ip: str = "10.0.0.5") -> SimpleNamespace:
    return SimpleNamespace(
        ip=ip,
        capabilities={ServerCapability.TERMINAL},
        get_server_connection=lambda: SimpleNamespace(
            credentials={"host": ip, "port": 22, "user": "mlox"}
        ),
    )


async def _visibility_for(selection: SelectionInfo) -> bool:
    app = ServerActionsTestApp()
    async with app.run_test() as pilot:
        actions = app.query_one(ServerActions)
        actions.selection = selection
        await pilot.pause()
        return actions.display


def test_actions_are_visible_for_bundle_and_server_selections() -> None:
    server = _terminal_server()

    assert asyncio.run(
        _visibility_for(
            SelectionInfo(
                type="bundle",
                bundle=SimpleNamespace(server=server),
            )
        )
    )
    assert asyncio.run(
        _visibility_for(SelectionInfo(type="server", server=server))
    )


def test_actions_are_hidden_for_non_server_selections() -> None:
    assert not asyncio.run(_visibility_for(SelectionInfo(type="root")))
    assert not asyncio.run(
        _visibility_for(
            SelectionInfo(type="service", service=SimpleNamespace(name="service"))
        )
    )


async def _click_open_terminal(monkeypatch) -> list[object]:
    launched: list[object] = []
    monkeypatch.setattr(
        "mlox.application.use_cases.servers.launch_external_ssh_terminal",
        launched.append,
    )
    server = _terminal_server()

    app = ServerActionsTestApp()
    async with app.run_test() as pilot:
        actions = app.query_one(ServerActions)
        actions.selection = SelectionInfo(type="server", server=server)
        await pilot.pause()
        await pilot.click("#open-server-terminal")
        await pilot.pause()
    return launched


def test_open_terminal_button_launches_selected_server(monkeypatch) -> None:
    launched = asyncio.run(_click_open_terminal(monkeypatch))

    assert len(launched) == 1
    assert launched[0].ip == "10.0.0.5"


async def _open_terminal_with_binding(monkeypatch, selection) -> list[object]:
    launched: list[object] = []
    monkeypatch.setattr(
        "mlox.application.use_cases.servers.launch_external_ssh_terminal",
        launched.append,
    )

    from mlox.tui.screens.dashboard.screen import DashboardScreen

    class DashboardBindingTestApp(App):
        def __init__(self) -> None:
            super().__init__()
            project = SimpleNamespace(
                name="test-project",
                infrastructure=SimpleNamespace(bundles=[]),
            )
            self.workspace = SimpleNamespace(
                name=project.name,
                infrastructure=project.infrastructure,
            )

        def compose(self) -> ComposeResult:
            yield DashboardScreen()

    app = DashboardBindingTestApp()
    async with app.run_test() as pilot:
        screen = app.query_one(DashboardScreen)
        screen._apply_selection(selection)
        await pilot.pause()
        await pilot.press("O")
        await pilot.pause()
    return launched


def test_open_terminal_binding_launches_for_server_selection(monkeypatch) -> None:
    server = _terminal_server()

    launched = asyncio.run(
        _open_terminal_with_binding(
            monkeypatch,
            SelectionInfo(type="server", server=server),
        )
    )

    assert launched == [server]


def test_open_terminal_binding_does_nothing_for_root_selection(monkeypatch) -> None:
    launched = asyncio.run(
        _open_terminal_with_binding(
            monkeypatch,
            SelectionInfo(type="root"),
        )
    )

    assert launched == []


def test_open_terminal_binding_does_nothing_for_bundle_selection(monkeypatch) -> None:
    server = _terminal_server()
    bundle = SimpleNamespace(server=server)

    launched = asyncio.run(
        _open_terminal_with_binding(
            monkeypatch,
            SelectionInfo(type="bundle", bundle=bundle, server=server),
        )
    )

    assert launched == []


def test_open_terminal_binding_does_nothing_for_connector_server(monkeypatch) -> None:
    server = SimpleNamespace(
        ip="connector",
        capabilities={"connector"},
        get_server_connection=lambda: SimpleNamespace(credentials={}),
    )

    launched = asyncio.run(
        _open_terminal_with_binding(
            monkeypatch,
            SelectionInfo(type="server", server=server),
        )
    )

    assert launched == []


async def _open_terminal_binding_available(selection) -> bool:
    class DashboardBindingTestApp(App):
        def __init__(self) -> None:
            super().__init__()
            self.workspace = SimpleNamespace(
                name="test-project",
                infrastructure=SimpleNamespace(bundles=[]),
            )

        def compose(self) -> ComposeResult:
            yield DashboardScreen()

    app = DashboardBindingTestApp()
    async with app.run_test() as pilot:
        screen = app.query_one(DashboardScreen)
        screen._apply_selection(selection)
        await pilot.pause()
        return bool(screen.check_action("open_terminal", ()))


def test_open_terminal_binding_is_available_only_for_terminal_capable_servers() -> None:
    terminal_server = _terminal_server()
    connector_server = SimpleNamespace(
        ip="connector",
        capabilities={"connector"},
        get_server_connection=lambda: SimpleNamespace(credentials={}),
    )

    assert asyncio.run(
        _open_terminal_binding_available(
            SelectionInfo(type="server", server=terminal_server)
        )
    )
    assert not asyncio.run(
        _open_terminal_binding_available(
            SelectionInfo(type="bundle", bundle=SimpleNamespace(server=terminal_server))
        )
    )
    assert not asyncio.run(
        _open_terminal_binding_available(
            SelectionInfo(type="server", server=connector_server)
        )
    )


async def _server_action_button_presentation() -> list[str | None]:
    app = ServerActionsTestApp()
    async with app.run_test() as pilot:
        actions = app.query_one(ServerActions)
        actions.selection = SelectionInfo(type="server", server=_terminal_server())
        await pilot.pause()
        row = actions.query_one("#server-action-buttons")
        return [
            child.id
            for child in row.children
            if getattr(child, "display", True)
        ]


def test_server_actions_keep_terminal_and_credentials_together() -> None:
    button_ids = asyncio.run(_server_action_button_presentation())

    assert button_ids == [
        "open-server-terminal",
        "toggle-server-credentials",
        "refresh-runtime-info",
    ]


async def _edit_tags_button_visibility() -> tuple[bool, bool]:
    server = _terminal_server()
    bundle = SimpleNamespace(server=server)
    app = ServerActionsTestApp()
    async with app.run_test() as pilot:
        actions = app.query_one(ServerActions)
        button = actions.query_one("#edit-bundle-tags", Button)

        actions.selection = SelectionInfo(type="bundle", bundle=bundle, server=server)
        await pilot.pause()
        bundle_display = button.display

        actions.selection = SelectionInfo(type="server", server=server)
        await pilot.pause()
        server_display = button.display
        return bundle_display, server_display


def test_edit_tags_button_is_only_visible_for_bundle_selection() -> None:
    bundle_display, server_display = asyncio.run(_edit_tags_button_visibility())

    assert bundle_display is True
    assert server_display is False


async def _open_terminal_button_visibility(selection: SelectionInfo) -> bool:
    app = ServerActionsTestApp()
    async with app.run_test() as pilot:
        actions = app.query_one(ServerActions)
        actions.selection = selection
        await pilot.pause()
        return actions.query_one("#open-server-terminal", Button).display


def test_open_terminal_button_requires_terminal_capable_server_selection() -> None:
    terminal_server = _terminal_server()
    connector_server = SimpleNamespace(
        ip="connector",
        capabilities={"connector"},
        get_server_connection=lambda: SimpleNamespace(credentials={}),
    )

    assert asyncio.run(
        _open_terminal_button_visibility(
            SelectionInfo(type="server", server=terminal_server)
        )
    )
    assert not asyncio.run(
        _open_terminal_button_visibility(
            SelectionInfo(type="bundle", bundle=SimpleNamespace(server=terminal_server))
        )
    )
    assert not asyncio.run(
        _open_terminal_button_visibility(
            SelectionInfo(type="server", server=connector_server)
        )
    )


async def _credentials_button_visibility(selection: SelectionInfo) -> bool:
    app = ServerActionsTestApp()
    async with app.run_test() as pilot:
        actions = app.query_one(ServerActions)
        actions.selection = selection
        await pilot.pause()
        return actions.query_one("#toggle-server-credentials", Button).display


def test_credentials_button_requires_terminal_capable_server_selection() -> None:
    terminal_server = _terminal_server()
    connector_server = SimpleNamespace(
        ip="connector",
        capabilities={"connector"},
        get_server_connection=lambda: SimpleNamespace(credentials={}),
    )

    assert asyncio.run(
        _credentials_button_visibility(
            SelectionInfo(type="server", server=terminal_server)
        )
    )
    assert not asyncio.run(
        _credentials_button_visibility(
            SelectionInfo(type="bundle", bundle=SimpleNamespace(server=terminal_server))
        )
    )
    assert not asyncio.run(
        _credentials_button_visibility(
            SelectionInfo(type="server", server=connector_server)
        )
    )


async def _action_titles_for_bundle_and_server() -> tuple[str, str]:
    server = SimpleNamespace(ip="10.0.0.5")
    bundle = SimpleNamespace(server=server)
    app = ServerActionsTestApp()
    async with app.run_test() as pilot:
        actions = app.query_one(ServerActions)
        actions.selection = SelectionInfo(type="bundle", bundle=bundle, server=server)
        await pilot.pause()
        bundle_title = str(actions.border_title)

        actions.selection = SelectionInfo(type="server", server=server)
        await pilot.pause()
        server_title = str(actions.border_title)
        return bundle_title, server_title


def test_actions_title_matches_bundle_or_server_selection() -> None:
    bundle_title, server_title = asyncio.run(_action_titles_for_bundle_and_server())

    assert bundle_title == "Bundle Actions"
    assert server_title == "Server Actions"


async def _server_info_refresh_button_presentation() -> tuple[str, str]:
    app = DashboardServerInfoTestApp()
    async with app.run_test() as pilot:
        screen = app.query_one(DashboardScreen)
        screen._apply_selection(
            SelectionInfo(type="server", server=SimpleNamespace())
        )
        await pilot.pause()
        button = app.query_one("#refresh-runtime-info", Button)
        panel = app.query_one(ServerInfoPanel)
        return str(button.label), str(panel.border_title)


def test_server_actions_has_server_info_refresh_button() -> None:
    label, title = asyncio.run(_server_info_refresh_button_presentation())

    assert label == "Refresh Server Info"
    assert title == "Server Info"


async def _bundle_runtime_refresh_button_label() -> str:
    server = SimpleNamespace(ip="10.0.0.5")
    bundle = SimpleNamespace(server=server)
    app = DashboardServerInfoTestApp()
    async with app.run_test() as pilot:
        screen = app.query_one(DashboardScreen)
        screen._apply_selection(
            SelectionInfo(type="bundle", bundle=bundle, server=server)
        )
        await pilot.pause()
        return str(app.query_one("#refresh-runtime-info", Button).label)


def test_bundle_actions_has_backend_refresh_button() -> None:
    assert asyncio.run(_bundle_runtime_refresh_button_label()) == (
        "Refresh Backend Info"
    )


async def _server_info_titles_for_bundle_and_server() -> tuple[str, str]:
    server = SimpleNamespace(ip="10.0.0.5")
    bundle = SimpleNamespace(server=server)
    app = DashboardServerInfoTestApp()
    async with app.run_test() as pilot:
        screen = app.query_one(DashboardScreen)
        panel = app.query_one(ServerInfoPanel)
        screen._apply_selection(
            SelectionInfo(type="bundle", bundle=bundle, server=server)
        )
        await pilot.pause()
        bundle_title = str(panel.border_title)

        screen._apply_selection(SelectionInfo(type="server", server=server))
        await pilot.pause()
        server_title = str(panel.border_title)
        return bundle_title, server_title


def test_server_info_panel_title_matches_selection() -> None:
    bundle_title, server_title = asyncio.run(_server_info_titles_for_bundle_and_server())

    assert bundle_title == "Backend"
    assert server_title == "Server Info"


async def _click_server_info() -> str:
    server = SimpleNamespace(
        ip="10.0.0.5",
        get_server_info=lambda no_cache=True: {
            "cpu_count": 4,
            "host": "demo-host",
        },
        get_backend_status=lambda: {"backend.is_running": True},
    )

    app = DashboardServerInfoTestApp()
    async with app.run_test() as pilot:
        screen = app.query_one(DashboardScreen)
        screen._apply_selection(SelectionInfo(type="server", server=server))
        await pilot.pause()
        app.query_one(ServerInfoPanel).load_selected_info(refresh=True)
        for _ in range(20):
            await pilot.pause()
            rendered = _render_server_info_panel(app)
            if "demo-host" in rendered:
                return rendered
        return _render_server_info_panel(app)


def test_server_info_panel_renders_server_information() -> None:
    rendered = asyncio.run(_click_server_info())

    assert "System" in rendered
    assert "CPU Cores" in rendered
    assert "4" in rendered
    assert "Host" in rendered
    assert "demo-host" in rendered
    assert "cpu_count:" not in rendered
    assert "host:" not in rendered
    assert "Backend" not in rendered
    assert "backend.is_running: True" not in rendered


async def _click_vps_server_info() -> str:
    server = SimpleNamespace(
        ip="10.0.0.5",
        get_server_info=lambda no_cache=True: {
            "bug_report_url": "https://bugs.launchpad.net/ubuntu/",
            "cpu_count": 6.0,
            "home_url": "https://www.ubuntu.com/",
            "host": "vmd167437.contaboserver.net",
            "id": "ubuntu",
            "id_like": "debian",
            "logo": "ubuntu-logo",
            "name": "Ubuntu",
            "pretty_name": "Ubuntu 24.04.3 LTS",
            "privacy_policy_url": "https://www.ubuntu.com/legal/terms",
            "ram_gb": 12.0,
            "storage_gb": 145.0,
            "support_url": "https://help.ubuntu.com/",
            "ubuntu_codename": "noble",
            "version": "24.04",
            "version_codename": "noble",
            "version_id": "24.04",
        },
        get_backend_status=lambda: {"backend.is_running": True},
    )

    app = DashboardServerInfoTestApp()
    async with app.run_test() as pilot:
        screen = app.query_one(DashboardScreen)
        screen._apply_selection(SelectionInfo(type="server", server=server))
        await pilot.pause()
        app.query_one(ServerInfoPanel).load_selected_info(refresh=True)
        for _ in range(20):
            await pilot.pause()
            rendered = _render_server_info_panel(app)
            if "vmd167437" in rendered:
                return rendered
        return _render_server_info_panel(app)


def test_vps_server_info_is_compact_and_filters_noisy_os_metadata() -> None:
    rendered = asyncio.run(_click_vps_server_info())

    assert "System" in rendered
    assert "Host" in rendered
    assert "vmd167437.contaboserver.net" in rendered
    assert "OS" in rendered
    assert "Ubuntu 24.04.3 LTS" in rendered
    assert "CPU Cores" in rendered
    assert "RAM (GiB)" in rendered
    assert "Storage (GiB)" in rendered
    assert "https://bugs.launchpad.net/ubuntu/" not in rendered
    assert "https://www.ubuntu.com/" not in rendered
    assert "ubuntu-logo" not in rendered


async def _click_bundle_backend_info() -> str:
    server = SimpleNamespace(
        ip="10.0.0.5",
        get_server_info=lambda no_cache=True: {"host": "demo-host"},
        get_backend_status=lambda: {
            "backend.is_running": True,
            "docker.is_running": True,
            "docker.is_enabled": True,
            "docker.version": {
                "Client": {"Version": "29.0.0"},
                "Server": {"Version": "29.0.0"},
            },
            "docker.containers": [
                {
                    "Names": "mlflow",
                    "Image": "ghcr.io/mlflow/mlflow:v3",
                    "State": "running",
                    "Status": "Up 2 hours",
                    "Ports": "0.0.0.0:5000->5000/tcp",
                    "Labels": "too,noisy,to,render",
                }
            ],
        },
    )
    bundle = SimpleNamespace(name="dev", server=server)

    app = DashboardServerInfoTestApp()
    async with app.run_test() as pilot:
        screen = app.query_one(DashboardScreen)
        screen._apply_selection(
            SelectionInfo(type="bundle", bundle=bundle, server=server)
        )
        await pilot.pause()
        app.query_one(ServerInfoPanel).load_selected_info(refresh=True)
        for _ in range(20):
            await pilot.pause()
            rendered = _render_server_info_panel(app)
            if "Containers" in rendered and "Client: 29.0.0" in rendered:
                return rendered
        return _render_server_info_panel(app)


def test_bundle_info_panel_renders_backend_information() -> None:
    rendered = asyncio.run(_click_bundle_backend_info())

    assert "Docker Backend" not in rendered
    assert "Backend Running" not in rendered
    assert "Docker: yes" in rendered
    assert "Enabled: yes" in rendered
    assert "Client: 29.0.0" in rendered
    assert "Server: 29.0.0" in rendered
    assert "Containers: 1" in rendered
    assert "yes" in rendered
    assert "Containers" in rendered
    assert "mlflow" in rendered
    assert "ghcr.io/mlflow/mlflow" in rendered
    assert "5000->5000" in rendered
    assert "too,noisy,to,render" not in rendered
    assert "host: demo-host" not in rendered


async def _click_kubernetes_backend_info(backend_info: dict) -> str:
    server = SimpleNamespace(
        ip="10.0.0.5",
        get_server_info=lambda no_cache=True: {"host": "demo-host"},
        get_backend_status=lambda: backend_info,
    )
    bundle = SimpleNamespace(name="dev", server=server)

    app = DashboardServerInfoTestApp()
    async with app.run_test() as pilot:
        screen = app.query_one(DashboardScreen)
        screen._apply_selection(
            SelectionInfo(type="bundle", bundle=bundle, server=server)
        )
        await pilot.pause()
        app.query_one(ServerInfoPanel).load_selected_info(refresh=True)
        for _ in range(20):
            await pilot.pause()
            rendered = _render_server_info_panel(app)
            if "k3s:" in rendered:
                return rendered
        return _render_server_info_panel(app)


def test_kubernetes_backend_info_renders_node_table() -> None:
    rendered = asyncio.run(
        _click_kubernetes_backend_info(
            {
                "backend.is_running": True,
                "k3s-agent.is_running": False,
                "k3s.is_running": True,
                "k3s.nodes": [
                    {
                        "NAME": "vmd167437",
                        "STATUS": "Ready",
                        "ROLES": "control-plane,master",
                        "AGE": "272d",
                        "VERSION": "v1.33.4+k3s1",
                        "INTERNAL-IP": "167.86.78.67",
                        "EXTERNAL-IP": "<none>",
                        "OS-IMAGE": "Ubuntu 24.04.3 LTS",
                        "KERNEL-VERSION": "6.8.0-71-generic",
                        "CONTAINER-RUNTIME": "containerd://2.0.5-k3s2",
                    },
                    {
                        "NAME": "vmd168621",
                        "STATUS": "Ready",
                        "ROLES": "<none>",
                        "VERSION": "v1.33.5+k3s1",
                        "INTERNAL-IP": "161.97.91.15",
                        "OS-IMAGE": "Ubuntu 24.04.3 LTS",
                        "CONTAINER-RUNTIME": "containerd://2.1.4-k3s1",
                    },
                ],
            }
        )
    )

    assert "Backend: yes" in rendered
    assert "k3s: yes" in rendered
    assert "agent: no" in rendered
    assert "nodes: 2" in rendered
    assert "Kubernetes Nodes" in rendered
    assert "vmd167437" in rendered
    assert "vmd168621" in rendered
    assert "control-plane,master" in rendered
    assert "containerd://2.0.5-k3s2" in rendered
    assert "k3s.nodes:" not in rendered


def test_kubernetes_agent_backend_info_renders_compact_status_without_nodes() -> None:
    rendered = asyncio.run(
        _click_kubernetes_backend_info(
            {
                "backend.is_running": True,
                "k3s-agent.is_running": True,
                "k3s.is_running": False,
            }
        )
    )

    assert "Backend: yes" in rendered
    assert "k3s: no" in rendered
    assert "agent: yes" in rendered
    assert "nodes: -" in rendered
    assert "k3s-agent.is_running:" not in rendered
    assert "k3s.is_running:" not in rendered


async def _click_server_info_with_blocked_worker() -> tuple[bool, str]:
    release = threading.Event()

    def get_server_info(no_cache: bool = False) -> dict[str, str]:
        release.wait(timeout=2)
        return {"host": "demo-host"}

    server = SimpleNamespace(
        ip="10.0.0.5",
        get_server_info=get_server_info,
        get_backend_status=lambda: {"backend.is_running": True},
    )

    app = DashboardServerInfoTestApp()
    async with app.run_test() as pilot:
        screen = app.query_one(DashboardScreen)
        screen._apply_selection(SelectionInfo(type="server", server=server))
        await pilot.pause()
        app.query_one(ServerInfoPanel).load_selected_info(refresh=True)
        await pilot.pause()
        hidden_while_loading = app.query_one(ServerInfoPanel).display is False
        release.set()
        for _ in range(20):
            await pilot.pause()
            rendered = _render_server_info_panel(app)
            if "demo-host" in rendered:
                return hidden_while_loading, rendered
        return hidden_while_loading, _render_server_info_panel(app)


def test_server_info_button_loads_information_without_blocking_ui() -> None:
    hidden_while_loading, rendered = asyncio.run(_click_server_info_with_blocked_worker())

    assert hidden_while_loading is True
    assert "Host" in rendered
    assert "demo-host" in rendered


async def _click_server_info_with_markup_like_output() -> str:
    server = SimpleNamespace(
        ip="10.0.0.5",
        get_server_info=lambda no_cache=True: {
            "message": "[not-a-rich-tag]literal[/not-a-rich-tag]",
        },
        get_backend_status=lambda: {"backend.is_running": True},
    )

    app = DashboardServerInfoTestApp()
    async with app.run_test() as pilot:
        screen = app.query_one(DashboardScreen)
        screen._apply_selection(SelectionInfo(type="server", server=server))
        await pilot.pause()
        app.query_one(ServerInfoPanel).load_selected_info(refresh=True)
        for _ in range(20):
            await pilot.pause()
            rendered = _render_server_info_panel(app)
            if "not-a-rich-tag" in rendered:
                return rendered
        return _render_server_info_panel(app)


def test_server_info_renders_markup_like_output_as_literal_text() -> None:
    rendered = asyncio.run(_click_server_info_with_markup_like_output())

    assert "[not-a-rich-tag]literal[/not-a-rich-tag]" in rendered


async def _server_info_uses_session_cache() -> tuple[str, str, int]:
    calls = 0

    def get_server_info(no_cache: bool = False) -> dict[str, str]:
        nonlocal calls
        if no_cache:
            calls += 1
        return {"host": "cached"}

    server = SimpleNamespace(
        get_server_info=get_server_info,
        get_backend_status=lambda: {},
    )
    app = DashboardServerInfoTestApp()
    async with app.run_test() as pilot:
        screen = app.query_one(DashboardScreen)
        screen._apply_selection(SelectionInfo(type="server", server=server))
        await pilot.pause()
        app.query_one(ServerInfoPanel).load_selected_info()
        for _ in range(20):
            await pilot.pause()
            first = _render_server_info_panel(app)
            if "cached" in first:
                break

        app.query_one(ServerInfoPanel).load_selected_info()
        await pilot.pause()
        second = _render_server_info_panel(app)
        return first, second, calls


def test_server_info_is_cached_for_current_tui_session() -> None:
    first, second, calls = asyncio.run(_server_info_uses_session_cache())

    assert "cached" in first
    assert "cached" in second
    assert calls == 1


async def _server_info_resets_on_selection_change() -> str:
    first_server = SimpleNamespace(
        get_server_info=lambda no_cache=True: {"host": "first"},
        get_backend_status=lambda: {},
    )
    second_server = SimpleNamespace(
        get_server_info=lambda no_cache=True: {"host": "second"},
        get_backend_status=lambda: {},
    )
    app = DashboardServerInfoTestApp()
    async with app.run_test() as pilot:
        screen = app.query_one(DashboardScreen)
        screen._apply_selection(SelectionInfo(type="server", server=first_server))
        await pilot.pause()
        app.query_one(ServerInfoPanel).load_selected_info(refresh=True)
        await pilot.pause()

        screen._apply_selection(SelectionInfo(type="server", server=second_server))
        await pilot.pause()
        return _render_server_info_panel(app)


def test_server_info_is_cleared_after_selection_changes() -> None:
    rendered = asyncio.run(_server_info_resets_on_selection_change())

    assert "first" not in rendered


async def _reveal_credentials() -> tuple[str, str, str, str]:
    server = _terminal_server()
    server.mlox_user = SimpleNamespace(name="mlox-user", pw="mlox-password")
    server.remote_user = SimpleNamespace(ssh_passphrase="key-passphrase")
    app = ServerActionsTestApp()
    async with app.run_test() as pilot:
        actions = app.query_one(ServerActions)
        actions.selection = SelectionInfo(type="server", server=server)
        await pilot.pause()
        hidden = str(actions.query_one("#server-credentials", Static).render())

        await pilot.click("#toggle-server-credentials")
        await pilot.pause()
        revealed = str(actions.query_one("#server-credentials", Static).render())

        await pilot.click("#copy-server-password")
        password_clipboard = app.clipboard
        await pilot.click("#copy-server-passphrase")
        passphrase_clipboard = app.clipboard
        return hidden, revealed, password_clipboard, passphrase_clipboard


def test_credentials_are_hidden_then_revealed_and_copyable() -> None:
    hidden, revealed, password_clipboard, passphrase_clipboard = asyncio.run(
        _reveal_credentials()
    )

    assert "mlox-password" not in hidden
    assert "key-passphrase" not in hidden
    assert "mlox-user" in revealed
    assert "mlox-password" in revealed
    assert "key-passphrase" in revealed
    assert password_clipboard == "mlox-password"
    assert passphrase_clipboard == "key-passphrase"


async def _credentials_reset_on_selection_change() -> str:
    first_server = _terminal_server("10.0.0.5")
    first_server.mlox_user = SimpleNamespace(name="first", pw="first-password")
    first_server.remote_user = SimpleNamespace(ssh_passphrase="first-passphrase")
    second_server = _terminal_server("10.0.0.6")
    second_server.mlox_user = SimpleNamespace(name="second", pw="second-password")
    second_server.remote_user = SimpleNamespace(ssh_passphrase="second-passphrase")
    app = ServerActionsTestApp()
    async with app.run_test() as pilot:
        actions = app.query_one(ServerActions)
        actions.selection = SelectionInfo(type="server", server=first_server)
        await pilot.pause()
        await pilot.click("#toggle-server-credentials")
        await pilot.pause()

        actions.selection = SelectionInfo(type="server", server=second_server)
        await pilot.pause()
        return str(actions.query_one("#server-credentials", Static).render())


def test_credentials_are_hidden_after_selection_changes() -> None:
    rendered = asyncio.run(_credentials_reset_on_selection_change())

    assert "Credentials are hidden." in rendered
    assert "second-password" not in rendered
