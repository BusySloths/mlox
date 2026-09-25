"""Actions available for the selected infrastructure service."""

from __future__ import annotations

from typing import Optional

from textual import on
from textual.app import ComposeResult
from textual.containers import Container, Horizontal
from textual.message import Message
from textual.reactive import reactive
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Label, Select, Static

from mlox.application.use_cases.services import (
    list_service_web_ui_login_fields,
    service_can_restart,
    service_has_health,
    service_has_web_ui,
)
from mlox.service import ServiceCapability

from .model import SelectionInfo, get_service_capabilities


def service_supports_runtime_provider_binding(service: object | None) -> bool:
    """Return whether a service accepts either runtime provider binding."""

    capabilities = set(get_service_capabilities(service))
    return bool(
        capabilities
        & {
            ServiceCapability.SECRET_MANAGER_BINDING.value,
            ServiceCapability.TELEMETRY_BINDING.value,
        }
    )


def runtime_provider_options(
    infrastructure: object,
    capability: ServiceCapability,
    *,
    consumer_uuid: str = "",
) -> list[tuple[str, str]]:
    """Return provider labels and UUIDs matching one provider capability."""

    options: list[tuple[str, str]] = []
    for bundle in getattr(infrastructure, "bundles", []) or []:
        for service in getattr(bundle, "services", []) or []:
            service_uuid = str(getattr(service, "uuid", "") or "")
            if not service_uuid or service_uuid == consumer_uuid:
                continue
            if capability.value not in get_service_capabilities(service):
                continue
            name = str(getattr(service, "name", service_uuid) or service_uuid)
            options.append((name, service_uuid))
    return sorted(options, key=lambda option: option[0].lower())


class RuntimeProvidersDialog(
    ModalScreen[dict[str, str | None] | None]
):
    """Select independently bound secret-manager and telemetry providers."""

    def __init__(
        self,
        service: object,
        *,
        secret_manager_options: list[tuple[str, str]],
        telemetry_options: list[tuple[str, str]],
    ) -> None:
        super().__init__()
        self.service = service
        self.secret_manager_options = self._include_current(
            secret_manager_options,
            str(getattr(service, "secret_manager_uuid", "") or ""),
        )
        self.telemetry_options = self._include_current(
            telemetry_options,
            str(getattr(service, "telemetry_uuid", "") or ""),
        )
        capabilities = set(get_service_capabilities(service))
        self.supports_secret_manager = (
            ServiceCapability.SECRET_MANAGER_BINDING.value in capabilities
        )
        self.supports_telemetry = (
            ServiceCapability.TELEMETRY_BINDING.value in capabilities
        )

    @staticmethod
    def _include_current(
        options: list[tuple[str, str]], current_uuid: str
    ) -> list[tuple[str, str]]:
        if current_uuid and current_uuid not in {value for _, value in options}:
            return [(f"Current provider ({current_uuid})", current_uuid), *options]
        return options

    def compose(self) -> ComposeResult:
        service_name = str(getattr(self.service, "name", "service"))
        with Container(id="runtime-providers-dialog"):
            yield Label("Runtime Providers", id="runtime-providers-title")
            yield Static(
                f"Configure providers exposed to '{service_name}'. "
                "Select None to remove a binding.",
                id="runtime-providers-description",
            )
            if self.supports_secret_manager:
                yield Label("Secret manager", classes="runtime-provider-label")
                yield Select(
                    self.secret_manager_options,
                    value=self._current_value("secret_manager_uuid"),
                    prompt="None",
                    allow_blank=True,
                    id="runtime-secret-manager",
                )
            if self.supports_telemetry:
                yield Label("Telemetry", classes="runtime-provider-label")
                yield Select(
                    self.telemetry_options,
                    value=self._current_value("telemetry_uuid"),
                    prompt="None",
                    allow_blank=True,
                    id="runtime-telemetry",
                )
            with Horizontal(id="runtime-providers-actions"):
                yield Button("Cancel", id="cancel-runtime-providers")
                yield Button(
                    "Apply",
                    id="confirm-runtime-providers",
                    variant="success",
                )

    def _current_value(self, attribute: str):
        value = str(getattr(self.service, attribute, "") or "")
        return value or Select.BLANK

    @staticmethod
    def _selected_value(select: Select) -> str | None:
        return None if select.value is Select.BLANK else str(select.value)

    @on(Button.Pressed, "#cancel-runtime-providers")
    def handle_cancel(self, _: Button.Pressed) -> None:
        self.dismiss(None)

    @on(Button.Pressed, "#confirm-runtime-providers")
    def handle_confirm(self, _: Button.Pressed) -> None:
        values: dict[str, str | None] = {}
        if self.supports_secret_manager:
            values["secret_manager_uuid"] = self._selected_value(
                self.query_one("#runtime-secret-manager", Select)
            )
        if self.supports_telemetry:
            values["telemetry_uuid"] = self._selected_value(
                self.query_one("#runtime-telemetry", Select)
            )
        self.dismiss(values)


class RenameServiceDialog(ModalScreen[str | None]):
    """Modal prompt for changing a service display name."""

    def __init__(self, current_name: str) -> None:
        super().__init__()
        self.current_name = current_name

    def compose(self) -> ComposeResult:
        with Container(id="rename-service-dialog"):
            yield Label("Rename Service", id="rename-service-title")
            yield Input(
                value=self.current_name,
                placeholder="Service name",
                id="rename-service-name",
            )
            with Horizontal(id="rename-service-actions"):
                yield Button("Cancel", id="cancel-service-rename")
                yield Button("Rename", id="confirm-service-rename", variant="success")

    def on_mount(self) -> None:
        self.query_one("#rename-service-name", Input).focus()

    @on(Input.Submitted, "#rename-service-name")
    def handle_name_submitted(self, _: Input.Submitted) -> None:
        self._dismiss_with_name()

    @on(Button.Pressed, "#cancel-service-rename")
    def handle_cancel(self, _: Button.Pressed) -> None:
        self.dismiss(None)

    @on(Button.Pressed, "#confirm-service-rename")
    def handle_confirm(self, _: Button.Pressed) -> None:
        self._dismiss_with_name()

    def _dismiss_with_name(self) -> None:
        name = self.query_one("#rename-service-name", Input).value.strip()
        self.dismiss(name)


class RemoveServiceDialog(ModalScreen[bool]):
    """Confirmation prompt before tearing down and removing a service."""

    def __init__(self, service_name: str) -> None:
        super().__init__()
        self.service_name = service_name

    def compose(self) -> ComposeResult:
        with Container(id="remove-service-dialog"):
            yield Label("Remove Service", id="remove-service-title")
            yield Static(
                f"Do you really want to teardown and remove service '{self.service_name}'?",
                id="remove-service-message",
            )
            with Horizontal(id="remove-service-actions"):
                yield Button("Cancel", id="cancel-remove-service")
                yield Button(
                    "Teardown Service",
                    id="confirm-remove-service",
                    variant="error",
                )

    @on(Button.Pressed, "#cancel-remove-service")
    def handle_cancel(self, _: Button.Pressed) -> None:
        self.dismiss(False)

    @on(Button.Pressed, "#confirm-remove-service")
    def handle_confirm(self, _: Button.Pressed) -> None:
        self.dismiss(True)


class ServiceActions(Container):
    """Selection-aware controls for service nodes."""

    class RenameRequested(Message):
        """Request that the dashboard opens the service rename modal."""

    class OpenWebUIRequested(Message):
        """Request that the dashboard opens the selected service web UI."""

    class CheckHealthRequested(Message):
        """Request that the dashboard checks selected service health."""

    class RestartRequested(Message):
        """Request that the dashboard restarts the selected service."""

    class CopyWebUILoginRequested(Message):
        """Request that the dashboard copies one web UI login field."""

        def __init__(self, field: str) -> None:
            super().__init__()
            self.field = field

    class TeardownRequested(Message):
        """Request that the dashboard confirms service teardown."""

    class SetupRequested(Message):
        """Request that the dashboard sets up the selected service."""

    class ConfigureRuntimeProvidersRequested(Message):
        """Request the runtime provider configuration dialog."""

    selection: reactive[Optional[SelectionInfo]] = reactive(None)

    def compose(self) -> ComposeResult:
        with Horizontal(id="service-action-buttons"):
            with Horizontal(id="service-primary-action-buttons"):
                yield Button("Open Web UI", id="open-service-web-ui", variant="primary")
                yield Button(
                    "Copy Username",
                    id="copy-service-web-ui-username",
                    variant="primary",
                )
                yield Button(
                    "Copy Password",
                    id="copy-service-web-ui-password",
                    variant="primary",
                )
                yield Button(
                    "Copy Token",
                    id="copy-service-web-ui-token",
                    variant="primary",
                )
                yield Button("Check Health", id="check-service-health")
                yield Button("Runtime Providers", id="configure-runtime-providers")
                yield Button("Rename Service", id="rename-service", variant="success")
                yield Button("Setup Service", id="setup-service", variant="warning")
            with Horizontal(id="service-destructive-action-buttons"):
                yield Button("Restart Service", id="restart-service", variant="warning")
                yield Button("Teardown Service", id="teardown-service", variant="error")

    def on_mount(self) -> None:
        self.border_title = "Service Actions"
        self._update_visibility(self.selection)

    def watch_selection(self, selection: Optional[SelectionInfo]) -> None:
        self._update_visibility(selection)
        if self.is_mounted:
            self.set_loading(False)

    def _update_visibility(self, selection: Optional[SelectionInfo]) -> None:
        self.display = bool(
            selection and selection.type == "service" and selection.service
        )
        if self.is_mounted:
            self.query_one("#open-service-web-ui", Button).display = bool(
                self._has_initialized_web_ui_service(selection)
            )
            self._render_health_action(selection)
            self._render_web_ui_login_actions(selection)
            self._render_setup_action(selection)
            self._render_restart_action(selection)
            self.query_one("#configure-runtime-providers", Button).display = bool(
                selection
                and service_supports_runtime_provider_binding(selection.service)
            )

    def _render_web_ui_login_actions(
        self, selection: Optional[SelectionInfo]
    ) -> None:
        fields = set()
        if self._has_initialized_web_ui_service(selection):
            result = list_service_web_ui_login_fields(selection.service)
            if result.success and result.data:
                fields = set(result.data.get("fields", []))
        self.query_one("#copy-service-web-ui-username", Button).display = (
            "username" in fields
        )
        self.query_one("#copy-service-web-ui-password", Button).display = (
            "password" in fields
        )
        self.query_one("#copy-service-web-ui-token", Button).display = (
            "token" in fields
        )

    def _render_health_action(self, selection: Optional[SelectionInfo]) -> None:
        button = self.query_one("#check-service-health", Button)
        service = selection.service if selection else None
        button.display = bool(
            self.display
            and service
            and getattr(service, "state", "unknown") != "un-initialized"
            and service_has_health(service)
        )

    def _render_setup_action(self, selection: Optional[SelectionInfo]) -> None:
        button = self.query_one("#setup-service", Button)
        service = selection.service if selection else None
        button.display = bool(
            self.display
            and service
            and getattr(service, "state", "unknown") == "un-initialized"
        )

    def _render_restart_action(self, selection: Optional[SelectionInfo]) -> None:
        button = self.query_one("#restart-service", Button)
        service = selection.service if selection else None
        button.display = bool(self.display and service_can_restart(service))

    def _has_initialized_web_ui_service(
        self,
        selection: Optional[SelectionInfo],
    ) -> bool:
        service = selection.service if selection else None
        return bool(
            self.display
            and service
            and getattr(service, "state", "unknown") != "un-initialized"
            and service_has_web_ui(service)
        )

    def set_loading(self, loading: bool) -> None:
        open_web_ui = self.query_one("#open-service-web-ui", Button)
        copy_username = self.query_one("#copy-service-web-ui-username", Button)
        copy_password = self.query_one("#copy-service-web-ui-password", Button)
        copy_token = self.query_one("#copy-service-web-ui-token", Button)
        health = self.query_one("#check-service-health", Button)
        runtime_providers = self.query_one("#configure-runtime-providers", Button)
        rename = self.query_one("#rename-service", Button)
        setup = self.query_one("#setup-service", Button)
        restart = self.query_one("#restart-service", Button)
        teardown = self.query_one("#teardown-service", Button)
        open_web_ui.disabled = loading
        copy_username.disabled = loading
        copy_password.disabled = loading
        copy_token.disabled = loading
        health.disabled = loading
        runtime_providers.disabled = loading
        health.label = "Checking..." if loading else "Check Health"
        rename.disabled = loading
        setup.disabled = loading
        setup.label = "Setting up..." if loading else "Setup Service"
        restart.disabled = loading
        restart.label = "Restart Service"
        teardown.disabled = loading
        teardown.label = "Tearing down..." if loading else "Teardown Service"
        if not loading:
            self._update_visibility(self.selection)

    def set_health_loading(self, loading: bool) -> None:
        open_web_ui = self.query_one("#open-service-web-ui", Button)
        copy_username = self.query_one("#copy-service-web-ui-username", Button)
        copy_password = self.query_one("#copy-service-web-ui-password", Button)
        copy_token = self.query_one("#copy-service-web-ui-token", Button)
        health = self.query_one("#check-service-health", Button)
        runtime_providers = self.query_one("#configure-runtime-providers", Button)
        rename = self.query_one("#rename-service", Button)
        setup = self.query_one("#setup-service", Button)
        restart = self.query_one("#restart-service", Button)
        teardown = self.query_one("#teardown-service", Button)
        open_web_ui.disabled = loading
        copy_username.disabled = loading
        copy_password.disabled = loading
        copy_token.disabled = loading
        health.disabled = loading
        runtime_providers.disabled = loading
        health.label = "Checking..." if loading else "Check Health"
        rename.disabled = loading
        setup.disabled = loading
        restart.disabled = loading
        teardown.disabled = loading
        if not loading:
            self._update_visibility(self.selection)

    def set_restart_loading(self, loading: bool) -> None:
        open_web_ui = self.query_one("#open-service-web-ui", Button)
        copy_username = self.query_one("#copy-service-web-ui-username", Button)
        copy_password = self.query_one("#copy-service-web-ui-password", Button)
        copy_token = self.query_one("#copy-service-web-ui-token", Button)
        health = self.query_one("#check-service-health", Button)
        runtime_providers = self.query_one("#configure-runtime-providers", Button)
        rename = self.query_one("#rename-service", Button)
        setup = self.query_one("#setup-service", Button)
        restart = self.query_one("#restart-service", Button)
        teardown = self.query_one("#teardown-service", Button)
        open_web_ui.disabled = loading
        copy_username.disabled = loading
        copy_password.disabled = loading
        copy_token.disabled = loading
        health.disabled = loading
        runtime_providers.disabled = loading
        rename.disabled = loading
        setup.disabled = loading
        restart.disabled = loading
        restart.label = "Restarting..." if loading else "Restart Service"
        teardown.disabled = loading
        if not loading:
            self._update_visibility(self.selection)

    def set_runtime_provider_loading(self, loading: bool) -> None:
        """Disable service actions while provider bindings are being applied."""

        self.set_loading(loading)
        button = self.query_one("#configure-runtime-providers", Button)
        button.label = "Applying..." if loading else "Runtime Providers"

    @on(Button.Pressed, "#open-service-web-ui")
    def handle_open_web_ui(self, _: Button.Pressed) -> None:
        self.post_message(self.OpenWebUIRequested())

    @on(Button.Pressed, "#copy-service-web-ui-username")
    def handle_copy_web_ui_username(self, _: Button.Pressed) -> None:
        self.post_message(self.CopyWebUILoginRequested("username"))

    @on(Button.Pressed, "#copy-service-web-ui-password")
    def handle_copy_web_ui_password(self, _: Button.Pressed) -> None:
        self.post_message(self.CopyWebUILoginRequested("password"))

    @on(Button.Pressed, "#copy-service-web-ui-token")
    def handle_copy_web_ui_token(self, _: Button.Pressed) -> None:
        self.post_message(self.CopyWebUILoginRequested("token"))

    @on(Button.Pressed, "#check-service-health")
    def handle_check_health(self, _: Button.Pressed) -> None:
        self.post_message(self.CheckHealthRequested())

    @on(Button.Pressed, "#rename-service")
    def handle_rename(self, _: Button.Pressed) -> None:
        self.post_message(self.RenameRequested())

    @on(Button.Pressed, "#configure-runtime-providers")
    def handle_configure_runtime_providers(self, _: Button.Pressed) -> None:
        self.post_message(self.ConfigureRuntimeProvidersRequested())

    @on(Button.Pressed, "#setup-service")
    def handle_setup(self, _: Button.Pressed) -> None:
        self.post_message(self.SetupRequested())

    @on(Button.Pressed, "#restart-service")
    def handle_restart(self, _: Button.Pressed) -> None:
        self.post_message(self.RestartRequested())

    @on(Button.Pressed, "#teardown-service")
    def handle_teardown(self, _: Button.Pressed) -> None:
        self.post_message(self.TeardownRequested())
