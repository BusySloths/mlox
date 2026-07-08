"""Template panel for browsing server and service configs."""

from __future__ import annotations

from dataclasses import asdict, is_dataclass
from typing import Any, Optional

from rich.markup import escape
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from textual import on
from textual.app import ComposeResult
from textual.containers import Container, Horizontal, VerticalScroll
from textual.coordinate import Coordinate
from textual.message import Message
from textual.reactive import reactive
from textual.widgets import Button, DataTable, LoadingIndicator, Static
from textual.widgets._data_table import RowKey

from mlox.application.use_cases.servers import browse_server_templates
from mlox.application.use_cases.services import browse_service_templates

from .model import SelectionInfo, get_server_backends


class TemplateDataTable(DataTable):
    """DataTable that notifies its parent when the cursor moves."""

    def watch_cursor_coordinate(self, _old: object, _new: object) -> None:
        panel = self.query_ancestor(TemplatePanel)
        if panel:
            panel.show_current_row_details()


class TemplatePanel(Container):
    """Template browser for one template category."""

    class ConfigureTemplateRequested(Message):
        """Request setup for the currently selected template."""

        def __init__(self, config: Any, template_type: str = "server") -> None:
            super().__init__()
            self.config = config
            self.template_type = template_type

    selection: reactive[Optional[SelectionInfo]] = reactive(None)

    def __init__(
        self,
        *children,
        template_type: str,
        **kwargs,
    ) -> None:
        super().__init__(*children, **kwargs)
        self.template_type = template_type
        self._configs_by_key: dict[str, Any] = {}
        self.selected_config_id: str | None = None
        self._adding = False

    def compose(self) -> ComposeResult:
        with VerticalScroll(classes="template-scroll-wrapper"):
            table = TemplateDataTable(classes="template-table")
            table.cursor_type = "row"
            table.add_columns("Name", "Version", "Maintainer", "Path")
            yield table
            yield Static(classes="template-details")
            with Horizontal(id="template-action-row"):
                yield Button(
                    "Configure & Add Server",
                    id="configure-add-server",
                    variant="success",
                )
                yield LoadingIndicator(id="template-add-indicator")
                yield Static("Adding server...", id="template-add-status")

    @property
    def table(self) -> DataTable:
        return self.query_one(DataTable)

    @property
    def details(self) -> Static:
        return self.query_one(".template-details", Static)

    def on_mount(self) -> None:
        self._show_templates()
        self.set_adding(False)

    def watch_selection(self, _selection: Optional[SelectionInfo]) -> None:
        self._show_templates()

    def _show_templates(self) -> None:
        if self.template_type == "server":
            self._show_server_templates()
        elif self.template_type == "service":
            self._show_service_templates()
        else:
            self._show_default()
        self._update_action_visibility()

    def _show_default(self) -> None:
        message = Text.from_markup(
            "[b]Templates[/b]\n\nSelect a server to browse matching server configs or a service to browse service configs."
        )
        self.table.clear(columns=False)
        self._configs_by_key = {}
        self.selected_config_id = None
        self.details.update(Panel(message, title="Templates", border_style="green"))
        self._update_action_visibility()

    def _show_template_table(
        self, configs: list[Any], title: str, empty_message: str = "No templates found."
    ) -> None:
        table = self.table
        table.clear(columns=False)
        self._configs_by_key = {}
        self.selected_config_id = None
        if configs:
            for cfg in configs:
                key = str(getattr(cfg, "id", "") or getattr(cfg, "name", ""))
                self._configs_by_key[key] = cfg
                table.add_row(
                    getattr(cfg, "name", "-"),
                    str(getattr(cfg, "version", "-")),
                    getattr(cfg, "maintainer", "-"),
                    getattr(cfg, "path", "-"),
                    key=key,
                )
            first_key = next(iter(self._configs_by_key))
            table.cursor_coordinate = (0, 0)
            self._show_config_details(first_key, title)
        else:
            self.details.update(
                Panel(Text(empty_message), title=title, border_style="yellow")
            )
        self._update_action_visibility()

    def show_current_row_details(self) -> None:
        table = self.table
        if table.row_count == 0:
            return
        cursor_row = table.cursor_row
        if cursor_row < 0 or cursor_row >= table.row_count:
            return
        row_key = table.coordinate_to_cell_key(Coordinate(cursor_row, 0)).row_key
        self._show_config_details(row_key)

    def _show_server_templates(self) -> None:
        result = browse_server_templates()
        configs = result.data["configs"] if result.success and result.data else []
        self._show_template_table(configs, "Server Templates")

    def _show_service_templates(self) -> None:
        selection = self.selection
        backends = None
        if selection and selection.type == "bundle":
            server = selection.server or getattr(selection.bundle, "server", None)
            backends = set(get_server_backends(server))
        result = browse_service_templates(backends=backends)
        configs = result.data["configs"] if result.success and result.data else []
        self._show_template_table(
            configs,
            "Service Templates",
            empty_message="No compatible service templates found for this bundle.",
        )

    def _row_key_value(self, row_key: object) -> str:
        if isinstance(row_key, RowKey):
            return str(row_key.value)
        return str(row_key)

    def _show_config_details(self, row_key: object, title: str | None = None) -> None:
        key = self._row_key_value(row_key)
        config = self._configs_by_key.get(key)
        if not config:
            return
        self.selected_config_id = key
        self._update_action_visibility()

        detail_table = Table.grid(padding=(0, 1))
        detail_table.add_column("Field", style="cyan", justify="right")
        detail_table.add_column("Value", justify="left")
        for label, value in self._detail_rows(config):
            detail_table.add_row(label, self._format_detail_value(value))

        panel_title = title or getattr(config, "name", "Template")
        self.details.update(Panel(detail_table, title=panel_title, border_style="green"))

    def _detail_rows(self, config: Any) -> list[tuple[str, Any]]:
        build = getattr(config, "build", None)
        rows: list[tuple[str, Any]] = [
            ("ID", getattr(config, "id", "-")),
            ("Name", getattr(config, "name", "-")),
            ("Version", getattr(config, "version", "-")),
            ("Maintainer", getattr(config, "maintainer", "-")),
            ("Short description", getattr(config, "description_short", "-")),
            ("Description", getattr(config, "description", "-")),
            ("Requirements", getattr(config, "requirements", {})),
            ("Ports", getattr(config, "ports", {})),
            ("Capabilities", getattr(config, "capabilities", {})),
            ("Groups", getattr(config, "groups", {})),
        ]
        if build:
            rows.extend(
                [
                    ("Build class", getattr(build, "class_name", "-")),
                    ("Build params", getattr(build, "params", {})),
                ]
            )
        rows.extend(
            [
                ("Links", getattr(config, "links", {})),
                ("Path", getattr(config, "path", "-")),
            ]
        )
        return rows

    def _format_detail_value(self, value: Any) -> str:
        if value in (None, "", {}, []):
            return "-"
        if is_dataclass(value):
            value = asdict(value)
        if isinstance(value, dict):
            if not value:
                return "-"
            return "\n".join(
                f"{escape(str(key))}: {escape(self._format_detail_value(item))}"
                for key, item in value.items()
            )
        if isinstance(value, (list, tuple, set)):
            if not value:
                return "-"
            return ", ".join(escape(str(item)) for item in value)
        text = str(value)
        if len(text) > 500:
            text = text[:497] + "..."
        return escape(text)

    def selected_config(self) -> Any | None:
        if not self.selected_config_id:
            return None
        return self._configs_by_key.get(self.selected_config_id)

    def set_adding(self, adding: bool) -> None:
        self._adding = adding
        if not self.is_mounted:
            return
        button = self.query_one("#configure-add-server", Button)
        indicator = self.query_one("#template-add-indicator", LoadingIndicator)
        status = self.query_one("#template-add-status", Static)
        button.disabled = adding or not bool(self.selected_config())
        button.label = self._action_label(adding=adding)
        indicator.display = adding
        status.display = adding
        status.update("Adding service..." if self.template_type == "service" else "Adding server...")

    def _update_action_visibility(self) -> None:
        if not self.is_mounted:
            return
        action_row = self.query_one("#template-action-row", Horizontal)
        button = self.query_one("#configure-add-server", Button)
        action_row.display = self.template_type in {"server", "service"}
        button.label = self._action_label()
        button.disabled = self._adding or not bool(self.selected_config())
        self.query_one("#template-add-indicator", LoadingIndicator).display = self._adding
        status = self.query_one("#template-add-status", Static)
        status.display = self._adding
        status.update("Adding service..." if self.template_type == "service" else "Adding server...")

    def _action_label(self, *, adding: bool = False) -> str:
        if self.template_type == "service":
            return "Adding Service..." if adding else "Configure & Add Service"
        return "Adding Server..." if adding else "Configure & Add Server"

    @on(DataTable.RowHighlighted)
    def handle_row_highlighted(
        self, event: DataTable.RowHighlighted
    ) -> None:  # pragma: no cover - UI callback
        self._show_config_details(event.row_key)

    @on(DataTable.RowSelected)
    def handle_row_selected(
        self, event: DataTable.RowSelected
    ) -> None:  # pragma: no cover - UI callback
        self._show_config_details(event.row_key)

    @on(Button.Pressed, "#configure-add-server")
    def handle_configure_server_template(self, _: Button.Pressed) -> None:
        config = self.selected_config()
        if config:
            self.post_message(
                self.ConfigureTemplateRequested(config, self.template_type)
            )
