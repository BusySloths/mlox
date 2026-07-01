"""Textual UI helpers for the OpenBao secret-manager service."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from textual import on
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.widgets import Button, DataTable, Input, Select, Static

from mlox.application.use_cases.openbao import (
    APPLICATION_PERIOD_OPTIONS,
    create_application_credential,
    create_application_keyfile,
    describe_openbao,
    get_application_keyfile_password,
    mask_secret,
    refresh_application_credentials,
    renew_application_credential,
    renew_application_keyfile_password,
    revoke_application_credential,
    rotate_client_token,
    unseal_openbao,
)
from mlox.infra import Bundle, Infrastructure
from mlox.services.openbao import OpenBaoDockerService


class OpenBaoSettingsPanel(VerticalScroll):
    """OpenBao service settings for the Textual dashboard."""

    def __init__(
        self,
        infra: Infrastructure | None,
        bundle: Bundle | None,
        service: OpenBaoDockerService | Any,
    ) -> None:
        super().__init__()
        self.infra = infra
        self.bundle = bundle
        self.service = service
        self._applications: list[dict[str, Any]] = []
        self._application_names: list[str] = []
        self._busy = False

    def compose(self) -> ComposeResult:
        with Vertical(id="openbao-settings"):
            yield Static("Access", classes="openbao-section-title")
            yield Static(id="openbao-status", markup=False)
            with Horizontal(id="openbao-access-actions", classes="openbao-action-row"):
                yield Button(
                    "Copy Browser Password",
                    id="openbao-copy-browser-password",
                    variant="success",
                )
            yield Static("Application Credentials", classes="openbao-section-title")
            with Horizontal(id="openbao-application-form"):
                yield Input(
                    placeholder="application-name",
                    id="openbao-application-name",
                )
                yield Select(
                    [
                        (label, value)
                        for label, value in APPLICATION_PERIOD_OPTIONS.items()
                    ],
                    value=APPLICATION_PERIOD_OPTIONS["24 hours"],
                    id="openbao-application-period",
                )
                yield Button(
                    "Add Credential",
                    id="openbao-add-application",
                    variant="success",
                )
            with Horizontal(id="openbao-application-actions"):
                yield Button(
                    "Refresh Applications",
                    id="openbao-refresh-apps",
                    variant="primary",
                )
                yield Button(
                    "Renew Selected",
                    id="openbao-renew-app",
                    variant="success",
                )
                yield Button(
                    "Revoke Selected",
                    id="openbao-revoke-app",
                    variant="error",
                )
                yield Static("", id="openbao-keyfile-action-spacer")
                yield Button(
                    "Copy Keyfile Password",
                    id="openbao-copy-keyfile-password",
                    variant="success",
                )
                yield Button(
                    "Renew Keyfile Password",
                    id="openbao-renew-keyfile-password",
                    variant="warning",
                )
                yield Button(
                    "Download Keyfile",
                    id="openbao-download-keyfile",
                    variant="success",
                )
            table = DataTable(id="openbao-application-table")
            table.cursor_type = "row"
            table.add_columns(
                "Application",
                "Status",
                "TTL",
                "Renewable",
                "Period",
                "Keyfile Password",
                "Accessor",
            )
            yield table
            yield Static("Recovery", classes="openbao-section-title")
            with Horizontal(id="openbao-recovery-actions", classes="openbao-action-row"):
                yield Button("Unseal", id="openbao-unseal", variant="warning")
                yield Button(
                    "Rotate Client Token",
                    id="openbao-rotate-client",
                    variant="warning",
                )
            yield Static(id="openbao-help", markup=False)

    @property
    def status(self) -> Static:
        return self.query_one("#openbao-status", Static)

    @property
    def table(self) -> DataTable:
        return self.query_one("#openbao-application-table", DataTable)

    @property
    def help(self) -> Static:
        return self.query_one("#openbao-help", Static)

    def on_mount(self) -> None:
        self.status.update(Panel(Text("Loading OpenBao settings..."), title="OpenBao"))
        self.help.update(self._help_panel())
        self._set_busy(True)
        self._run_operation(
            lambda: describe_openbao(self.infra, self.service),
            self._show_settings_result,
            group="openbao-load",
        )

    @on(Button.Pressed, "#openbao-copy-browser-password")
    def handle_copy_browser_password(self, _: Button.Pressed) -> None:
        password = str(getattr(self.service, "admin_password", "") or "")
        if not password:
            self.notify("OpenBao browser password is not available.", severity="warning")
            return
        self.app.copy_to_clipboard(password)
        self.notify("OpenBao browser password copied.")

    @on(Button.Pressed, "#openbao-rotate-client")
    def handle_rotate_client(self, _: Button.Pressed) -> None:
        self._run_mutation(
            lambda: rotate_client_token(self.infra, self.service),
            group="openbao-rotate-client",
        )

    @on(Button.Pressed, "#openbao-unseal")
    def handle_unseal(self, _: Button.Pressed) -> None:
        self._run_mutation(
            lambda: unseal_openbao(self.infra, self.service),
            group="openbao-unseal",
        )

    @on(Button.Pressed, "#openbao-refresh-apps")
    def handle_refresh_apps(self, _: Button.Pressed) -> None:
        self._run_mutation(
            lambda: refresh_application_credentials(self.infra, self.service),
            group="openbao-refresh-apps",
        )

    @on(Button.Pressed, "#openbao-add-application")
    def handle_add_application(self, _: Button.Pressed) -> None:
        name = self.query_one("#openbao-application-name", Input).value.strip()
        period = str(self.query_one("#openbao-application-period", Select).value)
        if not name:
            self.notify("Application name is required.", severity="warning")
            return
        self._run_mutation(
            lambda: create_application_credential(
                self.infra,
                self.service,
                application_name=name,
                period=period,
            ),
            group="openbao-add-application",
        )

    @on(Button.Pressed, "#openbao-renew-app")
    def handle_renew_application(self, _: Button.Pressed) -> None:
        application = self._selected_application()
        if not application:
            self.notify("Select an application credential.", severity="warning")
            return
        self._run_mutation(
            lambda: renew_application_credential(self.infra, self.service, application),
            group="openbao-renew-app",
        )

    @on(Button.Pressed, "#openbao-copy-keyfile-password")
    def handle_copy_keyfile_password(self, _: Button.Pressed) -> None:
        application = self._selected_application()
        if not application:
            self.notify("Select an application credential.", severity="warning")
            return
        self._set_busy(True)

        def after(result) -> None:
            self._set_busy(False)
            if not result.success:
                self.notify(result.message, severity="error")
                return
            payload = result.data or {}
            self.app.copy_to_clipboard(str(payload.get("password") or ""))
            if payload.get("password_generated"):
                self._commit_workspace()
                self._run_operation(
                    lambda: describe_openbao(self.infra, self.service),
                    self._show_settings_result,
                    group="openbao-copy-keyfile-password-refresh",
                )
            self.notify(f"Copied keyfile password for {application}.")

        self._run_operation(
            lambda: get_application_keyfile_password(self.service, application),
            after,
            group="openbao-copy-keyfile-password",
        )

    @on(Button.Pressed, "#openbao-renew-keyfile-password")
    def handle_renew_keyfile_password(self, _: Button.Pressed) -> None:
        application = self._selected_application()
        if not application:
            self.notify("Select an application credential.", severity="warning")
            return
        self._run_mutation(
            lambda: renew_application_keyfile_password(self.service, application),
            group="openbao-renew-keyfile-password",
        )

    @on(Button.Pressed, "#openbao-download-keyfile")
    def handle_download_keyfile(self, _: Button.Pressed) -> None:
        application = self._selected_application()
        if not application:
            self.notify("Select an application credential.", severity="warning")
            return
        self._set_busy(True)

        def after(result) -> None:
            if not result.success:
                self._set_busy(False)
                self.notify(result.message, severity="error")
                return

            payload = result.data or {}
            keyfile = str(payload.get("keyfile") or "")
            filename = str(payload.get("filename") or f"{application}.json")
            path = self._write_keyfile(filename, keyfile)
            self._commit_workspace()
            self.notify(f"Downloaded OpenBao keyfile to {path}.")
            self._run_operation(
                lambda: describe_openbao(self.infra, self.service),
                self._show_settings_result,
                group="openbao-download-keyfile-refresh",
            )

        self._run_operation(
            lambda: create_application_keyfile(self.infra, self.service, application),
            after,
            group="openbao-download-keyfile",
        )

    @on(Button.Pressed, "#openbao-revoke-app")
    def handle_revoke_application(self, _: Button.Pressed) -> None:
        application = self._selected_application()
        if not application:
            self.notify("Select an application credential.", severity="warning")
            return
        self._run_mutation(
            lambda: revoke_application_credential(self.infra, self.service, application),
            group="openbao-revoke-app",
        )

    def _run_mutation(self, operation, *, group: str) -> None:
        self._set_busy(True)

        def after(result) -> None:
            if not result.success:
                self._set_busy(False)
                self.notify(result.message, severity="error")
                return
            self._commit_workspace()
            self.notify(result.message)
            self._run_operation(
                lambda: describe_openbao(self.infra, self.service),
                self._show_settings_result,
                group=f"{group}-refresh",
            )

        self._run_operation(operation, after, group=group)

    def _run_operation(self, operation, callback, *, group: str) -> None:
        app = self.app

        def run() -> None:
            result = operation()
            app.call_from_thread(callback, result)

        app.run_worker(run, thread=True, exclusive=True, group=group)

    def _show_settings_result(self, result) -> None:
        self._set_busy(False)
        if not result.success:
            self.status.update(
                Panel(Text(result.message, style="bold red"), title="OpenBao")
            )
            return

        payload = result.data or {}
        applications = list(payload.get("applications", []))
        self.status.update(self._status_panel(payload, applications))
        self._populate_applications(applications)
        if payload.get("passwords_generated"):
            self._commit_workspace()

    def _status_panel(
        self,
        payload: dict[str, Any],
        applications: list[dict[str, Any]],
    ) -> Panel:
        status = payload.get("status", {})
        access = payload.get("access", {})
        recovery = payload.get("recovery", {})

        table = Table.grid(expand=True, padding=(0, 2))
        table.add_column("Label", style="cyan", no_wrap=True)
        table.add_column("Value")
        table.add_row("Initialized", "Yes" if status.get("initialized") else "No")
        table.add_row("Seal", "Sealed" if status.get("sealed") else "Open")
        table.add_row("Client TTL", str(status.get("client_token_ttl", 0)))
        table.add_row("Applications", str(len(applications)))
        table.add_row("Address", str(access.get("address") or "-"))
        table.add_row("Mount", str(access.get("mount_path") or "-"))
        table.add_row("Browser Login", self._browser_login(access))
        table.add_row("Client Token", mask_secret(str(access.get("client_token") or "")))
        table.add_row("Accessor", str(access.get("client_token_accessor") or "-"))
        table.add_row("Root Token", mask_secret(str(recovery.get("root_token") or "")))
        table.add_row("Unseal Keys", str(recovery.get("unseal_key_count", 0)))

        token_error = str(status.get("client_token_error") or "")
        if token_error:
            table.add_row("Token Error", Text(token_error, style="bold red"))

        return Panel(table, title="OpenBao", border_style="green")

    def _browser_login(self, access: dict[str, Any]) -> Text:
        text = Text()
        text.append(str(access.get("userpass_path") or "userpass"))
        text.append(" / ")
        text.append(str(access.get("admin_username") or "-"))
        password = str(access.get("admin_password") or "")
        if password:
            text.append(" / ")
            text.append(mask_secret(password), style="bold yellow")
        return text

    def _populate_applications(self, rows: list[dict[str, Any]]) -> None:
        self._applications = rows
        self._application_names = []
        table = self.table
        table.clear(columns=False)
        for row in rows:
            application = str(row.get("application") or "")
            if not application:
                continue
            self._application_names.append(application)
            table.add_row(
                application,
                str(row.get("status", "-")),
                str(row.get("ttl", "-")),
                "Yes" if row.get("renewable") else "No",
                str(row.get("period", "-")),
                str(row.get("keyfile_password_status", "-")),
                str(row.get("accessor", "-")),
                key=application,
            )
        if self._application_names:
            table.cursor_coordinate = (0, 0)

    def _help_panel(self) -> Panel:
        return Panel(
            Text(
                "OpenBao stores shared mlox secrets and application credentials. "
                "Root and unseal material are shown only masked here; use recovery "
                "actions carefully."
            ),
            title="Usage",
            border_style="cyan",
        )

    def _selected_application(self) -> str:
        row = self.table.cursor_row
        if row < 0 or row >= len(self._application_names):
            return ""
        return self._application_names[row]

    def _set_busy(self, busy: bool) -> None:
        self._busy = busy
        for button in self.query(Button):
            button.disabled = busy

    def _commit_workspace(self) -> None:
        workspace = getattr(self.app, "workspace", None)
        commit = getattr(workspace, "commit", None)
        if callable(commit):
            commit()

    def _write_keyfile(self, filename: str, keyfile: str) -> Path:
        target_dir = Path.home() / "Downloads"
        if not target_dir.exists():
            target_dir = Path.cwd()
        target = target_dir / (Path(filename).name or "openbao-keyfile.json")
        target.write_text(keyfile, encoding="utf-8")
        return target


def settings(
    infra: Infrastructure,
    bundle: Bundle,
    service: OpenBaoDockerService,
) -> OpenBaoSettingsPanel:
    return OpenBaoSettingsPanel(infra, bundle, service)
