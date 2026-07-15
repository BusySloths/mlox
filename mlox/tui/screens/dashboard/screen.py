"""Main dashboard screen composition."""

from __future__ import annotations

from textual import on
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, VerticalScroll
from textual.screen import ModalScreen, Screen
from textual.widget import Widget
from textual.widgets import (
    Button,
    Footer,
    Header,
    Label,
    LoadingIndicator,
    Static,
    TabPane,
    TabbedContent,
    Tabs,
)

from .app_log_panel import AppLogPanel
from .bundle_tags import EditBundleTagsDialog, RenameBundleDialog
from .firewall_panel import FirewallPanel
from .history_panel import HistoryPanel
from .log_panel import LogPanel
from .model import SelectionChanged, SelectionInfo, is_bundle_initialized
from .models_panel import ModelsPanel
from .monitor_panel import MonitorPanel
from .overview_panel import OverviewPanel
from .project_actions import ProjectActions, RenameProjectDialog
from .repository_panel import RepositoryPanel
from .server_actions import ServerActions
from .server_info_panel import ServerInfoPanel
from .service_actions import (
    RemoveServiceDialog,
    RenameServiceDialog,
    ServiceActions,
)
from .secret_manager_panel import SecretManagerPanel
from .template_panel import TemplatePanel
from .tree import InfraTree
from .workflow_panel import WorkflowPanel
from mlox.application.use_cases.servers import (
    add_server_from_template,
    check_server_health_in_workspace,
    materialize_server_template_params,
    remove_bundle,
    resolve_server_template_setup,
    setup_bundle,
)
from mlox.application.use_cases.project import (
    reload_project_workspace,
    rename_bundle,
    rename_project_workspace,
    update_bundle_tags,
)
from mlox.application.use_cases.services import (
    add_service_from_template,
    build_service_ui_widget,
    check_service_health_in_workspace,
    get_service_web_ui_login_value,
    materialize_service_template_params,
    open_service_web_ui,
    rename_service_in_workspace,
    resolve_service_template_setup,
    setup_service_in_workspace,
    teardown_service_in_workspace,
)
from mlox.tui.template_forms import (
    TemplateFormSpec,
    TemplateSetupDialog,
    valid_select_options,
)


FIREWALL_TAB_ID = "firewall-tab"
MONITOR_TAB_ID = "monitor-tab"
MODELS_TAB_ID = "models-tab"
WORKFLOW_TAB_ID = "workflow-tab"
SERVICE_TUI_TAB_ID = "service-tui-tab"
SECRET_MANAGER_TAB_ID = "secret-manager-tab"
REPOSITORY_TAB_ID = "repository-tab"
SERVER_TEMPLATES_TAB_ID = "server-templates-tab"
SERVICE_TEMPLATES_TAB_ID = "service-templates-tab"
OVERVIEW_TAB_ID = "overview-tab"
LOGS_TAB_ID = "logs-tab"
SIDEBAR_DEFAULT_WIDTH = 44
SIDEBAR_MIN_WIDTH = 24
SIDEBAR_MAX_WIDTH = 72
SIDEBAR_STEP = 4


class RemoveBundleDialog(ModalScreen[bool]):
    """Confirmation prompt before removing a bundle."""

    def __init__(self, bundle_name: str) -> None:
        super().__init__()
        self.bundle_name = bundle_name

    def compose(self) -> ComposeResult:
        with Container(id="remove-bundle-dialog"):
            yield Label("Remove Bundle", id="remove-bundle-title")
            yield Static(
                f"Do you really want to remove bundle '{self.bundle_name}'?",
                id="remove-bundle-message",
            )
            with Horizontal(id="remove-bundle-actions"):
                yield Button("Cancel", id="cancel-remove-bundle")
                yield Button(
                    "Remove Bundle", id="confirm-remove-bundle", variant="error"
                )

    @on(Button.Pressed, "#cancel-remove-bundle")
    def handle_cancel(self, _: Button.Pressed) -> None:
        self.dismiss(False)

    @on(Button.Pressed, "#confirm-remove-bundle")
    def handle_confirm(self, _: Button.Pressed) -> None:
        self.dismiss(True)


class DashboardScreen(Screen):
    """Main dashboard shown after a successful login."""

    BINDINGS = [
        ("l", "toggle_app_logs", "Logs"),
        ("O", "open_terminal", "Open Terminal"),
        ("R", "reload_infrastructure", "Reload"),
        Binding("c", "copy_model_example", "Copy Curl", show=False, priority=True),
        Binding("enter", "reveal_secret", "Reveal Secret", show=False, priority=True),
        Binding(
            "ctrl+a",
            "activate_secret_manager",
            "Use Secret Manager",
            show=False,
            priority=True,
        ),
        ("[", "narrow_sidebar", "Narrow Sidebar"),
        ("]", "widen_sidebar", "Widen Sidebar"),
    ]

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._sidebar_width = SIDEBAR_DEFAULT_WIDTH
        self._requested_tab_id: str | None = None
        self._current_selection: SelectionInfo | None = None

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True, classes="app-header")
        with Container(id="main-area"):
            with Container(id="sidebar"):
                yield InfraTree()
            with Container(id="detail-panel"):
                with Container(id="upper-pane"):
                    with Horizontal(id="project-reload-loading"):
                        yield LoadingIndicator(id="project-reload-indicator")
                        yield Static("Reloading project...", id="project-reload-label")
                    with Horizontal(id="server-add-loading"):
                        yield LoadingIndicator(id="server-add-indicator")
                        yield Static("Adding server...", id="server-add-label")
                    with Horizontal(id="service-add-loading"):
                        yield LoadingIndicator(id="service-add-indicator")
                        yield Static("Adding service...", id="service-add-label")
                    with Horizontal(id="bundle-lifecycle-loading"):
                        yield LoadingIndicator(id="bundle-lifecycle-indicator")
                        yield Static(
                            "Setting up bundle...",
                            id="bundle-lifecycle-label",
                        )
                    with Horizontal(id="summary-pane"):
                        with TabbedContent(id="main-tabs"):
                            with TabPane("Overview", id=OVERVIEW_TAB_ID):
                                with VerticalScroll(id="overview-scroll"):
                                    yield OverviewPanel(id="selection-overview")
                                    yield ProjectActions(id="selection-project-actions")
                                    yield ServerInfoPanel(id="selection-server-info")
                                    yield ServerActions(id="selection-server-actions")
                                    yield ServiceActions(id="selection-service-actions")
                            with TabPane("History & Logs", id=LOGS_TAB_ID):
                                yield LogPanel(id="selection-logs")
                                yield HistoryPanel(id="selection-history")
                            with TabPane(
                                "Server Templates", id=SERVER_TEMPLATES_TAB_ID
                            ):
                                yield TemplatePanel(
                                    id="server-template-panel", template_type="server"
                                )
                            with TabPane("Firewall", id=FIREWALL_TAB_ID):
                                yield FirewallPanel(id="firewall-panel")
                            with TabPane("Secret Manager", id=SECRET_MANAGER_TAB_ID):
                                yield SecretManagerPanel(id="secret-manager-panel")
                            with TabPane("Monitor", id=MONITOR_TAB_ID):
                                yield MonitorPanel(id="monitor-panel")
                            with TabPane("Models", id=MODELS_TAB_ID):
                                yield ModelsPanel(id="models-panel")
                            with TabPane("Workflow", id=WORKFLOW_TAB_ID):
                                yield WorkflowPanel(id="workflow-panel")
                            with TabPane("Repositories", id=REPOSITORY_TAB_ID):
                                yield RepositoryPanel(id="repository-panel")
                            with TabPane(
                                "Service Templates", id=SERVICE_TEMPLATES_TAB_ID
                            ):
                                yield TemplatePanel(
                                    id="service-template-panel", template_type="service"
                                )
                            with TabPane("Service", id=SERVICE_TUI_TAB_ID):
                                yield Container(id="service-tui-container")
        yield AppLogPanel(id="app-log-drawer")
        yield Footer(classes="app-footer")

    def on_mount(self) -> None:
        tree = self.query_one(InfraTree)
        tree.populate_tree()
        self._set_service_tui_tab_visible(False)
        tree.expand_all()
        tree.move_cursor(tree.root)
        self._apply_selection(tree.root.data)
        self._set_project_reload_loading(False)
        self._set_server_add_loading(False)
        self._set_service_add_loading(False)
        self._set_bundle_lifecycle_loading(False)
        self._set_app_log_drawer_visible(False)
        self._apply_sidebar_width()

    def on_selection_changed(self, message: SelectionChanged) -> None:
        self._apply_selection(message.selection)

    def on_secret_manager_panel_active_manager_changed(
        self,
        _: SecretManagerPanel.ActiveManagerChanged,
    ) -> None:
        tree = self.query_one(InfraTree)
        tree.populate_tree()
        tree.expand_all()
        tree.move_cursor(tree.root)
        self._apply_selection(tree.root.data)

    @on(Button.Pressed, "#refresh-runtime-info")
    def handle_runtime_info_requested(self, _: Button.Pressed) -> None:
        server_info = self.query_one(ServerInfoPanel)
        if not server_info.load_selected_info(refresh=True):
            self.notify(
                "Select a bundle or server to refresh runtime information.",
                severity="warning",
            )

    @on(ServerActions.CheckHealthRequested)
    def handle_server_health_requested(
        self,
        _: ServerActions.CheckHealthRequested,
    ) -> None:
        selection = self.query_one(ServerActions).selection
        if not selection or selection.type != "server" or not selection.server:
            self.notify("Select a health-capable server.", severity="warning")
            return
        workspace = getattr(self.app, "workspace", None)
        if not workspace:
            self.notify(
                "Cannot check server health because the workspace is unavailable.",
                severity="error",
            )
            return

        self.query_one(ServerActions).set_health_loading(True)

        def run_health_check() -> None:
            result = check_server_health_in_workspace(workspace, selection.server)
            self.app.call_from_thread(
                self._finish_server_health_check,
                result,
                selection,
            )

        self.app.run_worker(
            run_health_check,
            thread=True,
            exclusive=True,
            group="server-health",
        )

    def _finish_server_health_check(self, result, selection: SelectionInfo) -> None:
        self.query_one(ServerActions).set_health_loading(False)
        if not result.success:
            self.notify(result.message, severity="error")
            return
        self._refresh_tree_after_server_health(selection)
        self.notify(result.message)

    @on(ServerInfoPanel.RuntimeInfoLoadStarted)
    def handle_runtime_info_load_started(
        self, _: ServerInfoPanel.RuntimeInfoLoadStarted
    ) -> None:
        self.query_one(ServerActions).set_runtime_info_loading(True)

    @on(ServerInfoPanel.RuntimeInfoLoadFinished)
    def handle_runtime_info_load_finished(
        self, _: ServerInfoPanel.RuntimeInfoLoadFinished
    ) -> None:
        self.query_one(ServerActions).set_runtime_info_loading(False)

    def _apply_selection(self, selection: SelectionInfo | None) -> None:
        self._current_selection = selection
        overview = self.query_one(OverviewPanel)
        overview.selection = selection
        server_actions = self.query_one(ServerActions)
        server_actions.selection = selection
        service_actions = self.query_one(ServiceActions)
        service_actions.selection = selection
        project_actions = self.query_one(ProjectActions)
        project_actions.selection = selection
        server_info = self.query_one(ServerInfoPanel)
        server_info.selection = selection
        logs = self.query_one(LogPanel)
        logs.selection = selection
        history = self.query_one(HistoryPanel)
        history.selection = selection
        self._clear_lazy_root_panels()
        for templates in self.query(TemplatePanel):
            templates.selection = selection
        self._update_template_tabs(selection)
        self._sync_active_root_panel()
        self._update_tui_panel(selection)
        self.refresh_bindings()

    @on(TabbedContent.TabActivated, "#main-tabs")
    def handle_main_tab_activated(self, _: TabbedContent.TabActivated) -> None:
        self._sync_active_root_panel()

    def _clear_lazy_root_panels(self) -> None:
        self.query_one(SecretManagerPanel).selection = None
        self.query_one(FirewallPanel).selection = None
        self.query_one(MonitorPanel).selection = None
        self.query_one(ModelsPanel).selection = None
        self.query_one(WorkflowPanel).selection = None
        self.query_one(RepositoryPanel).selection = None

    def _sync_active_root_panel(self) -> None:
        selection = self._current_selection
        if not selection or selection.type != "root":
            self._clear_lazy_root_panels()
            return

        tabs = self.query_one("#main-tabs", TabbedContent)
        panel_by_tab = {
            SECRET_MANAGER_TAB_ID: self.query_one(SecretManagerPanel),
            FIREWALL_TAB_ID: self.query_one(FirewallPanel),
            MONITOR_TAB_ID: self.query_one(MonitorPanel),
            MODELS_TAB_ID: self.query_one(ModelsPanel),
            WORKFLOW_TAB_ID: self.query_one(WorkflowPanel),
            REPOSITORY_TAB_ID: self.query_one(RepositoryPanel),
        }
        for tab_id, panel in panel_by_tab.items():
            panel.selection = selection if tabs.active == tab_id else None

    def action_copy_model_example(self) -> None:
        tabs = self.query_one("#main-tabs", TabbedContent)
        if tabs.active != MODELS_TAB_ID:
            return
        self.query_one(ModelsPanel).copy_current_example()

    @on(ProjectActions.RenameRequested)
    async def handle_project_rename_requested(
        self, _: ProjectActions.RenameRequested
    ) -> None:
        workspace = getattr(self.app, "workspace", None)
        if not workspace:
            self.notify(
                "Cannot rename project because the workspace is unavailable.",
                severity="error",
            )
            return
        current_name = str(getattr(workspace, "name", ""))
        await self.app.push_screen(
            RenameProjectDialog(current_name),
            self._rename_project_from_dialog,
        )

    def _rename_project_from_dialog(self, name: str | None) -> None:
        if name is None:
            return
        workspace = getattr(self.app, "workspace", None)
        if not workspace:
            self.notify(
                "Cannot rename project because the workspace is unavailable.",
                severity="error",
            )
            return

        result = rename_project_workspace(workspace, name)
        if not result.success:
            self.notify(result.message, severity="error")
            return

        tree = self.query_one(InfraTree)
        tree.populate_tree()
        tree.expand_all()
        tree.move_cursor(tree.root)
        self._apply_selection(tree.root.data)
        self.notify(result.message)

    @on(ServerActions.EditTagsRequested)
    async def handle_bundle_tags_requested(
        self, _: ServerActions.EditTagsRequested
    ) -> None:
        selection = self.query_one(ServerActions).selection
        if not selection or selection.type != "bundle" or not selection.bundle:
            self.notify("Select a bundle to edit tags.", severity="warning")
            return

        current_tags = self._clean_tags(getattr(selection.bundle, "tags", []) or [])
        await self.app.push_screen(
            EditBundleTagsDialog(
                bundle_name=str(getattr(selection.bundle, "name", "-")),
                current_tags=current_tags,
                available_tags=self._project_tags(current_tags),
            ),
            lambda tags: self._update_bundle_tags_from_dialog(selection, tags),
        )

    @on(ServerActions.RenameBundleRequested)
    async def handle_bundle_rename_requested(
        self, _: ServerActions.RenameBundleRequested
    ) -> None:
        selection = self.query_one(ServerActions).selection
        if not selection or selection.type != "bundle" or not selection.bundle:
            self.notify("Select a bundle to rename.", severity="warning")
            return

        current_name = str(getattr(selection.bundle, "name", ""))
        await self.app.push_screen(
            RenameBundleDialog(current_name),
            lambda name: self._rename_bundle_from_dialog(selection, name),
        )

    @on(Button.Pressed, "#add-bundle-from-server-template")
    def handle_project_add_bundle_requested(self, event: Button.Pressed) -> None:
        event.stop()
        self._set_tab_visible(SERVER_TEMPLATES_TAB_ID, True)
        self._request_tab_activation(SERVER_TEMPLATES_TAB_ID)
        self.notify("Choose a server template to create a new bundle.")

    def _activate_server_templates_tab(self) -> None:
        tabs = self.query_one("#main-tabs", TabbedContent)
        try:
            tabs.active = SERVER_TEMPLATES_TAB_ID
        except Tabs.TabError:
            pass

    def _project_tags(self, preferred_tags: list[str]) -> list[str]:
        workspace = getattr(self.app, "workspace", None)
        bundles = getattr(getattr(workspace, "infrastructure", None), "bundles", [])
        tags = list(preferred_tags)
        for bundle in bundles or []:
            tags.extend(getattr(bundle, "tags", []) or [])
        return self._clean_tags(tags)

    def _clean_tags(self, tags: list[object]) -> list[str]:
        cleaned: list[str] = []
        seen: set[str] = set()
        for tag in tags:
            value = str(tag).strip()
            key = value.casefold()
            if value and key not in seen:
                seen.add(key)
                cleaned.append(value)
        return cleaned

    def _update_bundle_tags_from_dialog(
        self,
        selection: SelectionInfo,
        tags: list[str] | None,
    ) -> None:
        if tags is None:
            return
        workspace = getattr(self.app, "workspace", None)
        if not workspace:
            self.notify(
                "Cannot update bundle tags because the workspace is unavailable.",
                severity="error",
            )
            return

        result = update_bundle_tags(workspace, selection.bundle, tags)
        if not result.success:
            self.notify(result.message, severity="error")
            return

        self._apply_selection(selection)
        self.query_one(OverviewPanel).show_bundle(selection)
        self.notify(result.message)

    def _rename_bundle_from_dialog(
        self,
        selection: SelectionInfo,
        name: str | None,
    ) -> None:
        if name is None:
            return
        workspace = getattr(self.app, "workspace", None)
        if not workspace:
            self.notify(
                "Cannot rename bundle because the workspace is unavailable.",
                severity="error",
            )
            return

        result = rename_bundle(workspace, selection.bundle, name)
        if not result.success:
            self.notify(result.message, severity="error")
            return

        self._apply_selection(
            SelectionInfo(
                type="bundle",
                bundle=selection.bundle,
                server=selection.server or getattr(selection.bundle, "server", None),
            )
        )
        self.query_one(OverviewPanel).show_bundle(selection)
        self._refresh_tree_after_server_add(selection.bundle)
        self.notify(result.message)

    @on(ServerActions.SetupBundleRequested)
    def handle_setup_bundle_requested(
        self, _: ServerActions.SetupBundleRequested
    ) -> None:
        selection = self.query_one(ServerActions).selection
        if not selection or selection.type != "bundle" or not selection.bundle:
            self.notify("Select a bundle to set up.", severity="warning")
            return
        self._run_bundle_lifecycle(
            selection.bundle,
            setup=True,
            success_message="Bundle setup completed.",
        )

    @on(ServerActions.RemoveBundleRequested)
    async def handle_remove_bundle_requested(
        self, _: ServerActions.RemoveBundleRequested
    ) -> None:
        selection = self.query_one(ServerActions).selection
        if not selection or selection.type != "bundle" or not selection.bundle:
            self.notify("Select a bundle to remove.", severity="warning")
            return

        bundle_name = str(getattr(selection.bundle, "name", "-"))
        await self.app.push_screen(
            RemoveBundleDialog(bundle_name),
            lambda confirmed: self._remove_bundle_after_confirm(
                selection.bundle, confirmed
            ),
        )

    def _remove_bundle_after_confirm(
        self,
        bundle: object,
        confirmed: bool,
    ) -> None:
        if not confirmed:
            return
        self._run_bundle_lifecycle(
            bundle,
            setup=False,
            success_message="Bundle removed.",
        )

    def _run_bundle_lifecycle(
        self,
        bundle: object,
        *,
        setup: bool,
        success_message: str,
    ) -> None:
        workspace = getattr(self.app, "workspace", None)
        if not workspace:
            self.notify(
                "Cannot update bundle because the project workspace is unavailable.",
                severity="error",
            )
            return

        actions = self.query_one(ServerActions)
        actions.set_bundle_lifecycle_loading(True)
        self._set_bundle_lifecycle_loading(True, setup=setup)

        def run_operation() -> None:
            result = (
                setup_bundle(workspace, bundle)
                if setup
                else remove_bundle(workspace, bundle)
            )
            self.app.call_from_thread(
                self._finish_bundle_lifecycle,
                result,
                result.data.get("bundle") if setup and result.data else None,
                success_message,
            )

        self.app.run_worker(
            run_operation,
            thread=True,
            exclusive=True,
            group="bundle-lifecycle",
        )

    def _finish_bundle_lifecycle(
        self,
        result,
        bundle: object | None,
        success_message: str,
    ) -> None:
        self.query_one(ServerActions).set_bundle_lifecycle_loading(False)
        self._set_bundle_lifecycle_loading(False)
        if not result.success:
            self.notify(result.message, severity="error")
            return

        if bundle is not None:
            self._apply_selection(
                SelectionInfo(
                    type="bundle",
                    bundle=bundle,
                    server=getattr(bundle, "server", None),
                )
            )
        self._refresh_tree_after_server_add(bundle)
        self.notify(result.message or success_message)

    @on(ServiceActions.RenameRequested)
    async def handle_service_rename_requested(
        self, _: ServiceActions.RenameRequested
    ) -> None:
        selection = self.query_one(ServiceActions).selection
        if not selection or selection.type != "service" or not selection.service:
            self.notify("Select a service to rename.", severity="warning")
            return

        current_name = str(getattr(selection.service, "name", ""))
        await self.app.push_screen(
            RenameServiceDialog(current_name),
            lambda name: self._rename_service_from_dialog(selection, name),
        )

    def _rename_service_from_dialog(
        self,
        selection: SelectionInfo,
        name: str | None,
    ) -> None:
        if name is None:
            return
        workspace = getattr(self.app, "workspace", None)
        if not workspace:
            self.notify(
                "Cannot rename service because the workspace is unavailable.",
                severity="error",
            )
            return

        result = rename_service_in_workspace(workspace, selection.service, name)
        if not result.success:
            self.notify(result.message, severity="error")
            return

        self._refresh_tree_after_service_change(selection.bundle, selection.service)
        self.notify(result.message)

    @on(ServiceActions.OpenWebUIRequested)
    def handle_service_open_web_ui_requested(
        self, _: ServiceActions.OpenWebUIRequested
    ) -> None:
        selection = self.query_one(ServiceActions).selection
        if not selection or selection.type != "service" or not selection.service:
            self.notify("Select a service with a web UI.", severity="warning")
            return

        result = open_service_web_ui(selection.service)
        if not result.success:
            self.notify(result.message, severity="error")
            return
        self.notify(result.message)

    @on(ServiceActions.CopyWebUILoginRequested)
    def handle_service_copy_web_ui_login_requested(
        self, message: ServiceActions.CopyWebUILoginRequested
    ) -> None:
        selection = self.query_one(ServiceActions).selection
        if not selection or selection.type != "service" or not selection.service:
            self.notify("Select a service with web UI login details.", severity="warning")
            return

        field = message.field

        def resolve_login() -> None:
            result = get_service_web_ui_login_value(
                selection.service,
                field,
                bundle=selection.bundle,
            )
            self.app.call_from_thread(
                self._finish_service_copy_web_ui_login,
                result,
            )

        self.app.run_worker(
            resolve_login,
            thread=True,
            exclusive=False,
            group="service-web-ui-login",
        )

    def _finish_service_copy_web_ui_login(self, result) -> None:
        if not result.success:
            self.notify(result.message, severity="error")
            return
        payload = result.data or {}
        field = str(payload.get("field") or "login")
        value = str(payload.get("value") or "")
        if not value:
            self.notify(f"Web UI {field} is not available.", severity="warning")
            return
        self.app.copy_to_clipboard(value)
        self.notify(f"Copied service web UI {field}.")

    @on(ServiceActions.CheckHealthRequested)
    def handle_service_health_requested(
        self,
        _: ServiceActions.CheckHealthRequested,
    ) -> None:
        selection = self.query_one(ServiceActions).selection
        if not selection or selection.type != "service" or not selection.service:
            self.notify("Select a health-capable service.", severity="warning")
            return
        workspace = getattr(self.app, "workspace", None)
        if not workspace:
            self.notify(
                "Cannot check service health because the workspace is unavailable.",
                severity="error",
            )
            return

        self.query_one(ServiceActions).set_health_loading(True)

        def run_health_check() -> None:
            result = check_service_health_in_workspace(workspace, selection.service)
            self.app.call_from_thread(
                self._finish_service_health_check,
                result,
                selection.bundle,
                selection.service,
            )

        self.app.run_worker(
            run_health_check,
            thread=True,
            exclusive=True,
            group="service-health",
        )

    def _finish_service_health_check(
        self,
        result,
        bundle: object | None,
        service: object | None,
    ) -> None:
        self.query_one(ServiceActions).set_health_loading(False)
        if not result.success:
            self.notify(result.message, severity="error")
            return
        self._refresh_tree_after_service_change(bundle, service)
        self.notify(result.message)

    @on(ServiceActions.SetupRequested)
    def handle_service_setup_requested(
        self, _: ServiceActions.SetupRequested
    ) -> None:
        selection = self.query_one(ServiceActions).selection
        if not selection or selection.type != "service" or not selection.service:
            self.notify("Select a service to set up.", severity="warning")
            return
        workspace = getattr(self.app, "workspace", None)
        if not workspace:
            self.notify(
                "Cannot set up service because the workspace is unavailable.",
                severity="error",
            )
            return

        self.query_one(ServiceActions).set_loading(True)

        def run_operation() -> None:
            result = setup_service_in_workspace(workspace, selection.service)
            self.app.call_from_thread(
                self._finish_service_setup,
                result,
                selection.bundle,
                selection.service,
            )

        self.app.run_worker(
            run_operation,
            thread=True,
            exclusive=True,
            group="service-lifecycle",
        )

    def _finish_service_setup(
        self,
        result,
        bundle: object | None,
        service: object | None,
    ) -> None:
        self.query_one(ServiceActions).set_loading(False)
        if not result.success:
            self.notify(result.message, severity="error")
            return
        self._refresh_tree_after_service_change(bundle, service)
        self.notify(result.message)

    @on(ServiceActions.TeardownRequested)
    async def handle_service_teardown_requested(
        self, _: ServiceActions.TeardownRequested
    ) -> None:
        selection = self.query_one(ServiceActions).selection
        if not selection or selection.type != "service" or not selection.service:
            self.notify("Select a service to teardown.", severity="warning")
            return

        service_name = str(getattr(selection.service, "name", "-"))
        await self.app.push_screen(
            RemoveServiceDialog(service_name),
            lambda confirmed: self._teardown_service_after_confirm(
                selection,
                confirmed,
            ),
        )

    def _teardown_service_after_confirm(
        self,
        selection: SelectionInfo,
        confirmed: bool,
    ) -> None:
        if not confirmed:
            return
        workspace = getattr(self.app, "workspace", None)
        if not workspace:
            self.notify(
                "Cannot teardown service because the workspace is unavailable.",
                severity="error",
            )
            return

        self.query_one(ServiceActions).set_loading(True)

        def run_operation() -> None:
            result = teardown_service_in_workspace(workspace, selection.service)
            self.app.call_from_thread(
                self._finish_service_teardown,
                result,
                selection.bundle,
            )

        self.app.run_worker(
            run_operation,
            thread=True,
            exclusive=True,
            group="service-lifecycle",
        )

    def _finish_service_teardown(self, result, bundle: object | None) -> None:
        self.query_one(ServiceActions).set_loading(False)
        if not result.success:
            self.notify(result.message, severity="error")
            return
        self._refresh_tree_after_service_change(bundle, None)
        self.notify(result.message)

    @on(TemplatePanel.ConfigureTemplateRequested)
    async def handle_template_configure_requested(
        self, message: TemplatePanel.ConfigureTemplateRequested
    ) -> None:
        if message.template_type == "service":
            await self._handle_service_template_configure_requested(message)
            return
        await self.handle_server_template_configure_requested(message)

    async def handle_server_template_configure_requested(
        self, message: TemplatePanel.ConfigureTemplateRequested
    ) -> None:
        workspace = getattr(self.app, "workspace", None)
        infra = getattr(workspace, "infrastructure", None)
        if not workspace or not infra:
            self.notify(
                "Cannot add a server because the project workspace is unavailable.",
                severity="error",
            )
            return

        result = resolve_server_template_setup(infra, message.config)
        if not result.success:
            self.notify(result.message, severity="error")
            return

        setup = result.data["setup"] if result.data else None
        if not isinstance(setup, TemplateFormSpec):
            self.notify(
                "Selected server template returned an unexpected setup form.",
                severity="error",
            )
            return

        await self.app.push_screen(
            TemplateSetupDialog(setup),
            lambda values: self._add_server_from_template_values(
                message.config, setup, values
            ),
        )

    async def _handle_service_template_configure_requested(
        self,
        message: TemplatePanel.ConfigureTemplateRequested,
    ) -> None:
        workspace = getattr(self.app, "workspace", None)
        infra = getattr(workspace, "infrastructure", None)
        selection = self.query_one("#service-template-panel", TemplatePanel).selection
        bundle = selection.bundle if selection and selection.type == "bundle" else None
        if not workspace or not infra:
            self.notify(
                "Cannot add a service because the project workspace is unavailable.",
                severity="error",
            )
            return
        if not bundle:
            self.notify("Select a bundle before adding a service.", severity="warning")
            return

        result = resolve_service_template_setup(infra, bundle, message.config)
        if not result.success:
            self.notify(result.message, severity="error")
            return

        setup = result.data["setup"] if result.data else None
        if not isinstance(setup, TemplateFormSpec):
            self.notify(
                "Selected service template returned an unexpected setup form.",
                severity="error",
            )
            return
        missing_options = self._missing_required_select_options(setup)
        if missing_options:
            self.notify(
                (
                    "Cannot add this service yet. Missing options for: "
                    + ", ".join(missing_options)
                    + "."
                ),
                severity="error",
            )
            return
        if not setup.fields:
            self._add_service_from_template_values(message.config, bundle, setup, {})
            return

        await self.app.push_screen(
            TemplateSetupDialog(setup),
            lambda values: self._add_service_from_template_values(
                message.config, bundle, setup, values
            ),
        )

    def _missing_required_select_options(self, setup: TemplateFormSpec) -> list[str]:
        return [
            field.label
            for field in setup.fields
            if (
                field.kind == "select"
                and field.required
                and not valid_select_options(field)
            )
        ]

    def _add_server_from_template_values(
        self,
        config: object,
        setup: TemplateFormSpec,
        values: dict[str, str] | None,
    ) -> None:
        if values is None:
            return
        workspace = getattr(self.app, "workspace", None)
        if not workspace:
            self.notify(
                "Cannot add a server because the project workspace is unavailable.",
                severity="error",
            )
            return

        panel = self.query_one("#server-template-panel", TemplatePanel)
        panel.set_adding(True)
        self._set_server_add_loading(True)

        def add_server() -> None:
            infra = getattr(workspace, "infrastructure", None)
            params_result = materialize_server_template_params(setup, values, infra)
            if not params_result.success:
                self.app.call_from_thread(
                    self._finish_server_template_add_error,
                    params_result.message,
                )
                return

            params = params_result.data["params"] if params_result.data else {}
            add_result = add_server_from_template(workspace, config, params)
            if not add_result.success:
                self.app.call_from_thread(
                    self._finish_server_template_add_error,
                    add_result.message,
                )
                return
            self.app.call_from_thread(self._finish_server_template_add, add_result)

        self.app.run_worker(
            add_server,
            thread=True,
            exclusive=True,
            group="server-template-add",
        )

    def _finish_server_template_add_error(self, message: str) -> None:
        self.query_one("#server-template-panel", TemplatePanel).set_adding(False)
        self._set_server_add_loading(False)
        self.notify(message, severity="error")

    def _finish_server_template_add(self, result) -> None:
        panel = self.query_one("#server-template-panel", TemplatePanel)
        panel.set_adding(False)
        self._set_server_add_loading(False)
        bundle = result.data.get("bundle") if result.data else None
        self._refresh_tree_after_server_add(bundle)
        self.notify(result.message)

    def _add_service_from_template_values(
        self,
        config: object,
        bundle: object,
        setup: TemplateFormSpec,
        values: dict[str, str] | None,
    ) -> None:
        if values is None:
            return
        workspace = getattr(self.app, "workspace", None)
        if not workspace:
            self.notify(
                "Cannot add a service because the project workspace is unavailable.",
                severity="error",
            )
            return

        panel = self.query_one("#service-template-panel", TemplatePanel)
        panel.set_adding(True)
        self._set_service_add_loading(True)

        def add_service() -> None:
            infra = getattr(workspace, "infrastructure", None)
            params_result = materialize_service_template_params(setup, values, infra)
            if not params_result.success:
                self.app.call_from_thread(
                    self._finish_service_template_add_error,
                    params_result.message,
                )
                return

            params = params_result.data["params"] if params_result.data else {}
            add_result = add_service_from_template(workspace, bundle, config, params)
            if not add_result.success:
                self.app.call_from_thread(
                    self._finish_service_template_add_error,
                    add_result.message,
                )
                return
            self.app.call_from_thread(
                self._finish_service_template_add,
                add_result,
                bundle,
            )

        self.app.run_worker(
            add_service,
            thread=True,
            exclusive=True,
            group="service-template-add",
        )

    def _finish_service_template_add_error(self, message: str) -> None:
        self.query_one("#service-template-panel", TemplatePanel).set_adding(False)
        self._set_service_add_loading(False)
        self.notify(message, severity="error")

    def _finish_service_template_add(self, result, bundle: object | None) -> None:
        panel = self.query_one("#service-template-panel", TemplatePanel)
        panel.set_adding(False)
        self._set_service_add_loading(False)
        service = result.data.get("service") if result.data else None
        self._refresh_tree_after_service_change(bundle, service)
        self.notify(result.message)

    def _refresh_tree_after_server_add(self, bundle: object | None) -> None:
        tree = self.query_one(InfraTree)
        tree.populate_tree()
        tree.expand_all()
        self.call_after_refresh(self._select_added_tree_node, bundle)

    def _select_added_tree_node(self, bundle: object | None) -> None:
        tree = self.query_one(InfraTree)
        tree.expand_all()
        if bundle is not None:
            for node in tree.root.children:
                selection = node.data
                if isinstance(selection, SelectionInfo) and selection.bundle is bundle:
                    tree.move_cursor(node)
                    self._apply_selection(selection)
                    return
        tree.move_cursor(tree.root)
        self._apply_selection(tree.root.data)

    def _refresh_tree_after_server_health(self, selection: SelectionInfo) -> None:
        tree = self.query_one(InfraTree)
        tree.populate_tree()
        tree.expand_all()
        self._select_server_tree_node(selection.server)
        self.call_after_refresh(self._select_server_tree_node, selection.server)

    def _select_server_tree_node(self, server: object | None) -> None:
        tree = self.query_one(InfraTree)
        tree.expand_all()
        for bundle_node in tree.root.children:
            for node in bundle_node.children:
                selection = node.data
                if (
                    isinstance(selection, SelectionInfo)
                    and selection.type == "server"
                    and selection.server is server
                ):
                    tree.move_cursor(node)
                    self._apply_selection(selection)
                    return
        tree.move_cursor(tree.root)
        self._apply_selection(tree.root.data)

    def _refresh_tree_after_service_change(
        self,
        bundle: object | None,
        service: object | None,
    ) -> None:
        tree = self.query_one(InfraTree)
        tree.populate_tree()
        tree.expand_all()
        self._select_service_tree_node(bundle, service)
        self.call_after_refresh(self._select_service_tree_node, bundle, service)

    def _select_service_tree_node(
        self,
        bundle: object | None,
        service: object | None,
    ) -> None:
        tree = self.query_one(InfraTree)
        tree.expand_all()
        for bundle_node in tree.root.children:
            bundle_selection = bundle_node.data
            if not isinstance(bundle_selection, SelectionInfo):
                continue
            if bundle_selection.bundle is not bundle:
                continue
            if service is None:
                tree.move_cursor(bundle_node)
                self._apply_selection(bundle_selection)
                return
            for node in bundle_node.children:
                selection = node.data
                if (
                    isinstance(selection, SelectionInfo)
                    and selection.service is service
                ):
                    tree.move_cursor(node)
                    self._apply_selection(selection)
                    return
        tree.move_cursor(tree.root)
        self._apply_selection(tree.root.data)

    def action_reload_infrastructure(self) -> None:
        workspace = getattr(self.app, "workspace", None)
        if not workspace:
            self.notify(
                "Cannot reload infrastructure because the project workspace is incomplete.",
                severity="error",
            )
            return
        project = str(workspace.path)

        self.notify(f"Reloading project infrastructure for {project}...")
        self._set_project_reload_loading(True)

        def reload_workspace() -> None:
            result = reload_project_workspace(workspace)
            if not result.success:
                self.app.call_from_thread(
                    self._show_reload_error,
                    result.message,
                )
                return
            self.app.call_from_thread(
                self._apply_reloaded_workspace,
                project,
            )

        self.app.run_worker(
            reload_workspace,
            thread=True,
            exclusive=True,
            group="project-reload",
        )

    def _show_reload_error(self, message: str) -> None:
        self._set_project_reload_loading(False)
        self.notify(message, severity="error")

    def _apply_reloaded_workspace(self, project: str) -> None:
        tree = self.query_one(InfraTree)
        tree.populate_tree()
        tree.expand_all()
        tree.move_cursor(tree.root)
        self._apply_selection(tree.root.data)
        self._set_project_reload_loading(False)
        self.notify(f"Reloaded project infrastructure for {project}.")

    def _update_template_tabs(self, selection: SelectionInfo | None) -> None:
        server_templates_visible = selection.type == "root" if selection else False
        service_templates_visible = (
            selection.type == "bundle" and is_bundle_initialized(selection.bundle)
            if selection
            else False
        )
        self._set_tab_visible(
            SERVER_TEMPLATES_TAB_ID,
            server_templates_visible,
        )
        self._set_tab_visible(
            SECRET_MANAGER_TAB_ID,
            selection.type == "root" if selection else False,
        )
        self._set_tab_visible(
            FIREWALL_TAB_ID,
            selection.type == "root" if selection else False,
        )
        self._set_tab_visible(
            MONITOR_TAB_ID,
            selection.type == "root" if selection else False,
        )
        self._set_tab_visible(
            MODELS_TAB_ID,
            selection.type == "root" if selection else False,
        )
        self._set_tab_visible(
            WORKFLOW_TAB_ID,
            selection.type == "root" if selection else False,
        )
        self._set_tab_visible(
            REPOSITORY_TAB_ID,
            selection.type == "root" if selection else False,
        )
        self._set_tab_visible(
            SERVICE_TEMPLATES_TAB_ID,
            service_templates_visible,
        )
        self._set_tab_visible(
            LOGS_TAB_ID,
            selection.type in {"server", "service"} if selection else False,
        )
        self._activate_requested_tab_if_visible(clear=False)

    def _request_tab_activation(self, tab_id: str) -> None:
        self._requested_tab_id = tab_id
        self._activate_requested_tab_if_visible(clear=False)
        self.call_after_refresh(self._activate_requested_tab_if_visible, False)
        self.set_timer(
            0.4,
            lambda: self._finish_requested_tab_activation(tab_id),
        )

    def _finish_requested_tab_activation(self, tab_id: str) -> None:
        if self._requested_tab_id != tab_id:
            return
        self._requested_tab_id = None
        self._update_template_tabs(self._current_selection)

    def _activate_requested_tab_if_visible(self, clear: bool = True) -> bool:
        requested = self._requested_tab_id
        if not requested:
            return False
        tabs = self.query_one("#main-tabs", TabbedContent)
        try:
            tab = tabs.get_tab(requested)
        except Tabs.TabError:
            if clear:
                self._requested_tab_id = None
            return False
        if tab.styles.display != "none":
            try:
                tabs.active = requested
            except Tabs.TabError:
                return False
            if clear:
                self._requested_tab_id = None
            return True
        if clear:
            self._requested_tab_id = None
        return False

    def _update_tui_panel(self, selection: SelectionInfo | None) -> None:
        container = self.query_one("#service-tui-container", Container)
        for child in list(container.children):
            child.remove()

        self._set_service_tui_tab_visible(False)

        if not selection or selection.type != "service" or not selection.service:
            self._mount_placeholder(
                container, "Select a service to inspect service-specific settings."
            )
            return

        workspace = getattr(self.app, "workspace", None)
        infra = workspace.infrastructure if workspace else None
        if not infra or not selection.bundle:
            self._mount_placeholder(
                container,
                "Service settings are unavailable because the infrastructure is not loaded.",
            )
            return

        result = build_service_ui_widget(infra, selection.bundle, selection.service)
        if not result.success:
            self._mount_placeholder(container, result.message)
            return

        widget = result.data["widget"] if result.data else None
        if not isinstance(widget, Widget):
            self._mount_placeholder(
                container,
                "Service settings provider returned an unexpected payload.",
            )
            return

        container.mount(widget)
        self._set_service_tui_tab_visible(True)

    def _set_service_tui_tab_visible(self, visible: bool) -> None:
        self._set_tab_visible(SERVICE_TUI_TAB_ID, visible)

    def _set_tab_visible(self, tab_id: str, visible: bool) -> None:
        tabs = self.query_one("#main-tabs", TabbedContent)
        try:
            if visible:
                tabs.show_tab(tab_id)
            else:
                if tab_id == self._requested_tab_id:
                    tabs.show_tab(tab_id)
                    return
                if tabs.active == tab_id:
                    tabs.active = OVERVIEW_TAB_ID
                tabs.hide_tab(tab_id)
        except Tabs.TabError:
            pass

    def action_toggle_app_logs(self) -> None:
        drawer = self.query_one("#app-log-drawer", AppLogPanel)
        self._set_app_log_drawer_visible(drawer.styles.display == "none")

    def action_open_terminal(self) -> None:
        server_actions = self.query_one(ServerActions)
        if not server_actions.can_open_terminal():
            self.notify(
                "Select a terminal-capable server to open an SSH terminal.",
                severity="warning",
            )
            return
        server_actions.open_terminal()

    def action_reveal_secret(self) -> None:
        self.query_one(SecretManagerPanel).action_reveal_selected()

    def action_activate_secret_manager(self) -> None:
        self.query_one(SecretManagerPanel).action_activate_selected_manager()

    def check_action(self, action: str, parameters: tuple[object, ...]) -> bool | None:
        if action == "open_terminal":
            try:
                return self.query_one(ServerActions).can_open_terminal()
            except Exception:
                return False
        if action == "reveal_secret":
            try:
                tabs = self.query_one("#main-tabs", TabbedContent)
                panel = self.query_one(SecretManagerPanel)
            except Exception:
                return False
            return tabs.active == SECRET_MANAGER_TAB_ID and panel.display
        if action == "activate_secret_manager":
            try:
                tabs = self.query_one("#main-tabs", TabbedContent)
                panel = self.query_one(SecretManagerPanel)
            except Exception:
                return False
            return (
                tabs.active == SECRET_MANAGER_TAB_ID
                and panel.display
                and panel.can_activate_selected_manager()
            )
        return super().check_action(action, parameters)

    def _set_app_log_drawer_visible(self, visible: bool) -> None:
        drawer = self.query_one("#app-log-drawer", AppLogPanel)
        drawer.styles.display = "block" if visible else "none"

    def _set_project_reload_loading(self, visible: bool) -> None:
        loading = self.query_one("#project-reload-loading", Horizontal)
        loading.display = visible

    def _set_server_add_loading(self, visible: bool) -> None:
        loading = self.query_one("#server-add-loading", Horizontal)
        loading.display = visible

    def _set_service_add_loading(self, visible: bool) -> None:
        loading = self.query_one("#service-add-loading", Horizontal)
        loading.display = visible

    def _set_bundle_lifecycle_loading(
        self,
        visible: bool,
        *,
        setup: bool = True,
    ) -> None:
        loading = self.query_one("#bundle-lifecycle-loading", Horizontal)
        label = self.query_one("#bundle-lifecycle-label", Static)
        label.update("Setting up bundle..." if setup else "Removing bundle...")
        loading.display = visible

    def action_narrow_sidebar(self) -> None:
        self._resize_sidebar(-SIDEBAR_STEP)

    def action_widen_sidebar(self) -> None:
        self._resize_sidebar(SIDEBAR_STEP)

    def _resize_sidebar(self, delta: int) -> None:
        self._sidebar_width = max(
            SIDEBAR_MIN_WIDTH,
            min(SIDEBAR_MAX_WIDTH, self._sidebar_width + delta),
        )
        self._apply_sidebar_width()

    def _apply_sidebar_width(self) -> None:
        sidebar = self.query_one("#sidebar", Container)
        sidebar.styles.width = self._sidebar_width

    def _mount_placeholder(self, container: Container, message: str) -> None:
        container.mount(Static(message, classes="service-tui-placeholder"))
