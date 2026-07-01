from __future__ import annotations

import asyncio
import io
from pathlib import Path
from types import SimpleNamespace

from rich.console import Console
from textual.app import App, ComposeResult
from textual.widgets import Button, Input, Select

from mlox.application.use_cases import openbao
from mlox.tui.services.openbao import OpenBaoSettingsPanel, settings


class FakeOpenBaoManager:
    def __init__(self, sealed: bool = False) -> None:
        self.sealed = sealed
        self.unsealed_with = []

    def lookup_self(self):
        return {"ttl": 3600, "renewable": True}

    def seal_status(self):
        return {"initialized": True, "sealed": self.sealed}

    def unseal(self, key: str):
        self.unsealed_with.append(key)
        self.sealed = False
        return {"sealed": False}

    @property
    def supports_keyfile_export(self) -> bool:
        return True

    def get_access_secrets(self):
        return {
            "address": "https://bao.test:8200",
            "token": "keyfile-token",
            "mount_path": "secret",
        }


class FakeOpenBaoService:
    uuid = "openbao-1"
    service_config_id = "openbao-docker"
    service_url = "https://bao.test:8200"
    mount_path = "secret"
    userpass_path = "userpass"
    admin_username = "mlox-admin"
    admin_password = "admin-password"
    client_token = "client-token-secret"
    client_token_accessor = "accessor-1234567890"
    client_token_renewable = True
    client_token_lease_duration = 0
    root_token = "root-token-secret"
    unseal_keys = ["unseal-key"]

    def __init__(self) -> None:
        self.manager = FakeOpenBaoManager()
        self.application_credentials = {
            "app": {
                "application_name": "app",
                "accessor": "accessor-app-123456",
                "lease_duration": 3600,
                "renewable": True,
                "period": "24h",
                "status": "active",
            }
        }
        self.calls = []

    def get_secret_manager(self, infra=None):
        return self.manager

    def get_root_secret_manager(self, infra=None):
        return self.manager

    def rotate_client_token(self, infra=None):
        self.calls.append(("rotate_client", None))
        self.client_token = "rotated-client-token"

    def create_application_credential(self, application_name, infra=None, *, period="24h"):
        self.calls.append(("create_application", application_name, period))
        self.application_credentials[application_name] = {
            "application_name": application_name,
            "accessor": f"accessor-{application_name}",
            "lease_duration": 3600,
            "renewable": True,
            "period": period,
            "status": "active",
        }
        return self.application_credentials[application_name]

    def create_keyfile_secret_manager(
        self,
        infra=None,
        *,
        application_name="",
        period="24h",
    ):
        self.calls.append(("create_keyfile", application_name, period))
        return self.manager

    def refresh_application_credentials(self, infra=None):
        self.calls.append(("refresh_applications", None))
        return self.application_credentials

    def renew_application_credential(self, application_name, infra=None, increment=None):
        self.calls.append(("renew_application", application_name, increment))

    def revoke_application_credential(self, application_name, infra=None):
        self.calls.append(("revoke_application", application_name))
        self.application_credentials.pop(application_name, None)


class OpenBaoPanelTestApp(App):
    def __init__(self, panel: OpenBaoSettingsPanel) -> None:
        super().__init__()
        self.panel = panel
        self.commits = 0
        self.copied_text = ""
        self.workspace = SimpleNamespace(commit=self._commit)

    def compose(self) -> ComposeResult:
        yield self.panel

    def _commit(self) -> None:
        self.commits += 1

    def copy_to_clipboard(self, text: str) -> None:
        self.copied_text = text


def _render_text(renderable: object) -> str:
    console = Console(file=io.StringIO(), record=True, width=120)
    console.print(renderable)
    return console.export_text()


def test_settings_returns_openbao_panel() -> None:
    service = FakeOpenBaoService()

    panel = settings(None, None, service)  # type: ignore[arg-type]

    assert isinstance(panel, OpenBaoSettingsPanel)


def test_describe_openbao_returns_access_and_applications() -> None:
    service = FakeOpenBaoService()

    result = openbao.describe_openbao(None, service)

    assert result.success
    assert result.data["status"]["initialized"] is True
    assert result.data["status"]["client_token_ttl"] == 3600
    assert result.data["access"]["admin_username"] == "mlox-admin"
    assert result.data["applications"][0]["application"] == "app"
    assert result.data["applications"][0]["keyfile_password_status"] == "Set"
    assert "keyfile_password" not in result.data["applications"][0]
    assert result.data["passwords_generated"] is True
    assert service.application_credentials["app"]["keyfile_password"]


def test_create_application_keyfile_generates_password_and_payload() -> None:
    service = FakeOpenBaoService()

    result = openbao.create_application_keyfile(None, service, "app")

    assert result.success
    assert result.data["application"] == "app"
    assert result.data["filename"] == "app.json"
    assert result.data["keyfile"]
    assert result.data["password"] == service.application_credentials["app"][
        "keyfile_password"
    ]
    assert ("create_keyfile", "app", "24h") in service.calls


def test_get_application_keyfile_password_generates_missing_password() -> None:
    service = FakeOpenBaoService()

    result = openbao.get_application_keyfile_password(service, "app")

    assert result.success
    assert result.data["password"]
    assert result.data["password_generated"] is True
    assert result.data["password"] == service.application_credentials["app"][
        "keyfile_password"
    ]


def test_renew_application_keyfile_password_replaces_password() -> None:
    service = FakeOpenBaoService()
    old_password = openbao.get_application_keyfile_password(service, "app").data[
        "password"
    ]

    result = openbao.renew_application_keyfile_password(service, "app")

    assert result.success
    assert service.application_credentials["app"]["keyfile_password"] != old_password


async def _render_openbao_panel() -> tuple[str, int]:
    service = FakeOpenBaoService()
    panel = OpenBaoSettingsPanel(None, None, service)
    app = OpenBaoPanelTestApp(panel)

    async with app.run_test() as pilot:
        await pilot.pause(0.2)
        status = _render_text(panel.status.content)
        rows = panel.table.row_count
    return status, rows


def test_openbao_panel_loads_status_and_applications() -> None:
    status, rows = asyncio.run(_render_openbao_panel())

    assert "OpenBao" in status
    assert "mlox-admin" in status
    assert rows == 1


async def _openbao_panel_controls() -> tuple[bool, bool, bool, bool, bool]:
    service = FakeOpenBaoService()
    panel = OpenBaoSettingsPanel(None, None, service)
    app = OpenBaoPanelTestApp(panel)

    async with app.run_test() as pilot:
        await pilot.pause(0.2)
        app_button = panel.query_one("#openbao-add-application", Button)
        copy_button = panel.query_one("#openbao-copy-keyfile-password", Button)
        download_button = panel.query_one("#openbao-download-keyfile", Button)
        name_input = panel.query_one("#openbao-application-name", Input)
        period_select = panel.query_one("#openbao-application-period", Select)
        return (
            not app_button.disabled,
            not copy_button.disabled,
            not download_button.disabled,
            not name_input.disabled,
            bool(period_select.value),
        )


def test_openbao_panel_exposes_application_form_controls() -> None:
    add_enabled, copy_enabled, download_enabled, input_enabled, has_period = asyncio.run(
        _openbao_panel_controls()
    )

    assert add_enabled
    assert copy_enabled
    assert download_enabled
    assert input_enabled
    assert has_period


async def _copy_browser_password_from_panel() -> str:
    service = FakeOpenBaoService()
    panel = OpenBaoSettingsPanel(None, None, service)
    app = OpenBaoPanelTestApp(panel)

    async with app.run_test() as pilot:
        await pilot.pause(0.2)
        panel.query_one("#openbao-copy-browser-password", Button).press()
        await pilot.pause()
        return app.copied_text


def test_openbao_panel_copies_browser_password() -> None:
    clipboard = asyncio.run(_copy_browser_password_from_panel())

    assert clipboard == "admin-password"


async def _copy_keyfile_password_from_panel() -> tuple[str, int]:
    service = FakeOpenBaoService()
    panel = OpenBaoSettingsPanel(None, None, service)
    app = OpenBaoPanelTestApp(panel)

    async with app.run_test() as pilot:
        await pilot.pause(0.2)
        panel.query_one("#openbao-copy-keyfile-password", Button).press()
        await pilot.pause(0.2)
        return app.copied_text, app.commits


def test_openbao_panel_copies_keyfile_password() -> None:
    clipboard, commits = asyncio.run(_copy_keyfile_password_from_panel())

    assert clipboard
    assert commits >= 1


async def _renew_keyfile_password_from_panel() -> tuple[str, str, int]:
    service = FakeOpenBaoService()
    old_password = openbao.get_application_keyfile_password(service, "app").data[
        "password"
    ]
    panel = OpenBaoSettingsPanel(None, None, service)
    app = OpenBaoPanelTestApp(panel)

    async with app.run_test() as pilot:
        await pilot.pause(0.2)
        panel.query_one("#openbao-renew-keyfile-password", Button).press()
        await pilot.pause(0.3)
        return (
            old_password,
            service.application_credentials["app"]["keyfile_password"],
            app.commits,
        )


def test_openbao_panel_renews_keyfile_password_and_commits() -> None:
    old_password, new_password, commits = asyncio.run(
        _renew_keyfile_password_from_panel()
    )

    assert new_password != old_password
    assert commits >= 1


async def _add_application_from_panel() -> tuple[list[tuple], int, int]:
    service = FakeOpenBaoService()
    panel = OpenBaoSettingsPanel(None, None, service)
    app = OpenBaoPanelTestApp(panel)

    async with app.run_test() as pilot:
        await pilot.pause(0.2)
        panel.query_one("#openbao-application-name").value = "new-app"
        panel.query_one("#openbao-add-application").press()
        await pilot.pause(0.2)
        return service.calls, app.commits, panel.table.row_count


def test_openbao_panel_adds_application_and_commits() -> None:
    calls, commits, rows = asyncio.run(_add_application_from_panel())

    assert ("create_application", "new-app", "24h") in calls
    assert commits == 2
    assert rows == 2


async def _download_keyfile_from_panel() -> tuple[list[tuple], int, Path, str]:
    service = FakeOpenBaoService()
    panel = OpenBaoSettingsPanel(None, None, service)
    app = OpenBaoPanelTestApp(panel)

    async with app.run_test() as pilot:
        await pilot.pause(0.2)
        panel.query_one("#openbao-download-keyfile", Button).press()
        await pilot.pause(0.3)
        path = Path.home() / "Downloads" / "app.json"
        return (
            service.calls,
            app.commits,
            path,
            service.application_credentials["app"]["keyfile_password"],
        )


def test_openbao_panel_downloads_application_keyfile(
    tmp_path: Path,
    monkeypatch,
) -> None:
    downloads = tmp_path / "Downloads"
    downloads.mkdir()
    monkeypatch.setenv("HOME", str(tmp_path))

    calls, commits, path, password = asyncio.run(_download_keyfile_from_panel())

    assert ("create_keyfile", "app", "24h") in calls
    assert commits >= 1
    assert password
    assert path.exists()
    assert path.read_text(encoding="utf-8").strip()
