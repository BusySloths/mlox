"""Template panel for browsing server and service configs."""

from __future__ import annotations

from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any, Callable, Optional

import yaml
from rich.panel import Panel
from rich.text import Text

from textual import on
from textual.app import ComposeResult
from textual.containers import Container, Horizontal, VerticalScroll
from textual.message import Message
from textual.reactive import reactive
from textual.screen import ModalScreen
from textual.widgets import Button, DataTable, Static, TextArea
from textual.widgets._data_table import RowKey

from mlox.application.use_cases.servers import browse_server_templates
from mlox.application.use_cases.services import browse_service_templates
from mlox.config import get_stacks_path
from mlox.tui.template_forms import TemplateFormSpec, TemplateSetupForm

from .model import SelectionInfo, get_server_backends


class TemplatePanel(Container):
    """Template browser for one template category."""

    class ConfigureTemplateRequested(Message):
        """Request setup for the currently selected template."""

        def __init__(self, config: Any) -> None:
            super().__init__()
            self.config = config

    class SourceRequested(Message):
        def __init__(self, name: str, origin: str, source: str) -> None:
            super().__init__()
            self.name, self.origin, self.source = name, origin, source

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

    def compose(self) -> ComposeResult:
        kind = "Service" if self.template_type == "service" else "Server"
        yield Static(f"{kind} templates", classes="template-heading")
        yield Static(
            "Use ↑ / ↓ to browse. Tab moves through the summary and actions.",
            classes="template-help",
        )
        yield Static(classes="template-count")
        with Horizontal(classes="template-browser"):
            table = DataTable(classes="template-table")
            table.cursor_type = "row"
            table.add_columns("Name", "Version")
            yield table
            with VerticalScroll(classes="template-scroll-wrapper"):
                yield Static(classes="template-details")
        with Horizontal(id="template-action-row"):
            yield Button(
                "Configure & Add Server",
                id="configure-add-server",
                variant="success",
            )
            yield Button("View configuration", id="view-template-source")
            yield Static(classes="template-action-spacer")
            yield Button("Close", id="close-template-browser")

    @property
    def table(self) -> DataTable:
        return self.query_one(DataTable)

    @property
    def details(self) -> Static:
        return self.query_one(".template-details", Static)

    def on_mount(self) -> None:
        self._show_templates()
        self.query_one("#close-template-browser", Button).display = isinstance(
            self.screen, TemplateBrowserDialog
        )

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
        self.query_one(".template-count", Static).update("")
        self.details.update(Panel(message, title="Templates", border_style="green"))
        self._update_action_visibility()

    def _show_template_table(
        self, configs: list[Any], title: str, empty_message: str = "No templates found."
    ) -> None:
        table = self.table
        table.clear(columns=False)
        self._configs_by_key = {}
        self.selected_config_id = None
        count_label = "template" if len(configs) == 1 else "templates"
        self.query_one(".template-count", Static).update(
            f"{len(configs)} {count_label} available"
        )
        if configs:
            for cfg in configs:
                key = str(getattr(cfg, "id", "") or getattr(cfg, "name", ""))
                self._configs_by_key[key] = cfg
                table.add_row(
                    getattr(cfg, "name", "-"),
                    str(getattr(cfg, "version", "-")),
                    key=key,
                )
            first_key = next(iter(self._configs_by_key))
            table.cursor_coordinate = (0, 0)
            self._show_config_details(first_key)
        else:
            self.details.update(
                Panel(Text(empty_message), title=title, border_style="yellow")
            )
        self._update_action_visibility()

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

    def _show_config_details(self, row_key: object) -> None:
        key = self._row_key_value(row_key)
        config = self._configs_by_key.get(key)
        if not config:
            return
        self.selected_config_id = key
        self._update_action_visibility()

        summary = Text()
        summary.append(str(getattr(config, "name", "Template")), style="bold white")
        summary.append(f"  ·  {getattr(config, 'version', '-')}", style="cyan")
        description = getattr(config, "description", None) or getattr(
            config, "description_short", ""
        )
        if description:
            summary.append("\n\n" + str(description).strip())
        for label, value in self._detail_rows(config):
            if value not in (None, "", {}, [], "-"):
                summary.append(f"\n\n{label.upper()}\n", style="bold cyan")
                if label == "Capabilities" and isinstance(value, dict):
                    summary.append_text(self._capability_pills(value))
                else:
                    summary.append(self._format_detail_value(value))
        self.details.update(
            Panel(summary, title="Overview", title_align="left", border_style="green")
        )

    def _detail_rows(self, config: Any) -> list[tuple[str, Any]]:
        capabilities = getattr(config, "declared_capabilities", None)
        return [
            (
                "Capabilities",
                capabilities() if callable(capabilities) else getattr(config, "capabilities", {}),
            ),
            ("Requirements", getattr(config, "requirements", {})),
            ("Ports", getattr(config, "ports", {})),
            ("Maintainer", getattr(config, "maintainer", "-")),
            ("Links", getattr(config, "links", {})),
        ]

    def _capability_pills(self, capabilities: dict[str, Any]) -> Text:
        palette = (
            "bold white on dark_blue",
            "bold white on dark_green",
            "bold black on bright_yellow",
            "bold white on dark_cyan",
            "bold black on bright_white",
        )
        result = Text()
        index = 0
        for category, values in capabilities.items():
            if not values:
                continue
            if result:
                result.append("\n")
            result.append(f"{str(category).replace('_', ' ').title()}\n", style="bold")
            items = sorted(values, key=str) if isinstance(values, set) else values
            if isinstance(items, str):
                items = [items]
            for position, item in enumerate(items):
                if position:
                    result.append(" ")
                label = str(item).replace("_", " ")
                result.append(f" {label} ", style=palette[index % len(palette)])
                index += 1
        return result

    def _format_detail_value(self, value: Any) -> str:
        if value in (None, "", {}, []):
            return "-"
        if is_dataclass(value):
            value = asdict(value)
        if isinstance(value, dict):
            if not value:
                return "-"
            return "\n".join(
                f"{str(key).replace('_', ' ').title()}: {self._format_detail_value(item)}"
                for key, item in value.items()
            )
        if isinstance(value, (list, tuple, set)):
            if not value:
                return "-"
            items = sorted(value, key=str) if isinstance(value, set) else value
            return ", ".join(str(item).replace("_", " ") for item in items)
        text = str(value)
        return text

    def selected_config(self) -> Any | None:
        if not self.selected_config_id:
            return None
        return self._configs_by_key.get(self.selected_config_id)

    def _update_action_visibility(self) -> None:
        if not self.is_mounted:
            return
        action_row = self.query_one("#template-action-row", Horizontal)
        button = self.query_one("#configure-add-server", Button)
        action_row.display = self.template_type in {"server", "service"}
        button.label = self._action_label()
        button.disabled = not bool(self.selected_config())
        self.query_one("#view-template-source", Button).disabled = not bool(
            self.selected_config()
        )

    def _action_label(self) -> str:
        if self.template_type == "service":
            return "Configure & Add Service"
        return "Configure & Add Server"

    @on(DataTable.RowHighlighted)
    def handle_row_highlighted(
        self, event: DataTable.RowHighlighted
    ) -> None:  # pragma: no cover - UI callback
        self._show_config_details(event.row_key)

    @on(Button.Pressed, "#configure-add-server")
    def handle_configure_server_template(self, _: Button.Pressed) -> None:
        config = self.selected_config()
        if config:
            self.post_message(
                self.ConfigureTemplateRequested(config)
            )

    @on(Button.Pressed, "#view-template-source")
    def handle_view_source(self) -> None:
        config = self.selected_config()
        if not config:
            return
        path = getattr(config, "path", "")
        prefix = "mlox-server" if self.template_type == "server" else "mlox"
        source_path = Path(get_stacks_path(prefix)) / path if path else None
        try:
            if source_path and source_path.is_file():
                source = source_path.read_text(encoding="utf-8")
                origin = f"Source: {source_path}"
            elif is_dataclass(config):
                data = asdict(config)
                data.pop("path", None)
                source = yaml.safe_dump(data, sort_keys=False, allow_unicode=True)
                origin = "Generated from the loaded configuration; original source unavailable."
            else:
                source = "The original configuration source is not available."
                origin = "Source unavailable"
        except (OSError, UnicodeError, yaml.YAMLError) as exc:
            source = f"Could not read the configuration: {exc}"
            origin = "Source unavailable"
        name = str(getattr(config, "name", "Template"))
        self.post_message(self.SourceRequested(name, origin, source))


class TemplateBrowserDialog(ModalScreen[tuple[Any, TemplateFormSpec, dict[str, str]] | None]):
    """Browse, inspect and configure a template within one modal screen."""

    BINDINGS = [("escape", "back", "Back")]

    def __init__(self, template_type: str, selection: SelectionInfo | None,
                 resolve: Callable[[Any], TemplateFormSpec | None]) -> None:
        super().__init__()
        self.template_type = template_type
        self.selection = selection
        self.resolve = resolve
        self.view = "browse"
        self._form_config: Any = None
        self._form_spec: TemplateFormSpec | None = None

    def compose(self) -> ComposeResult:
        with Container(id="template-browser-dialog"):
            yield TemplatePanel(template_type=self.template_type, id="modal-template-panel")
            with Container(id="template-source-view"):
                yield Static(id="template-source-title", markup=False)
                yield Static(id="template-source-origin", markup=False)
                yield TextArea("", read_only=True, show_line_numbers=True, id="template-source-content")
                yield Button("Back", id="back-template-source")
            yield Container(id="template-form-view")

    def on_mount(self) -> None:
        panel = self.query_one(TemplatePanel)
        panel.selection = self.selection
        self._show_view("browse")
        panel.table.focus()

    def _show_view(self, view: str) -> None:
        self.view = view
        self.query_one(TemplatePanel).display = view == "browse"
        self.query_one("#template-source-view").display = view == "source"
        self.query_one("#template-form-view").display = view == "form"
        self.query_one("#template-browser-dialog").set_class(view == "form", "setup-active")
        if view == "browse":
            self.query_one(TemplatePanel).table.focus()
        elif view == "source":
            self.query_one("#template-source-content", TextArea).focus()
        else:
            form = self.query_one(TemplateSetupForm)
            first = form.spec.fields[0] if form.spec.fields else None
            if first:
                form.query_one(f"#{form._field_id(first.name)}").focus()

    def action_back(self) -> None:
        if self.view == "browse":
            self.dismiss(None)
        else:
            self._show_view("browse")

    @on(Button.Pressed, "#close-template-browser")
    def close_browser(self) -> None:
        self.dismiss(None)

    @on(Button.Pressed, "#back-template-source")
    def back_from_source(self) -> None:
        self.action_back()

    @on(TemplatePanel.SourceRequested)
    def show_source(self, message: TemplatePanel.SourceRequested) -> None:
        message.stop()
        self.query_one("#template-source-title", Static).update(f"{message.name} · Configuration")
        self.query_one("#template-source-origin", Static).update(message.origin)
        self.query_one("#template-source-content", TextArea).load_text(message.source)
        self._show_view("source")

    @on(TemplatePanel.ConfigureTemplateRequested)
    async def configure(self, message: TemplatePanel.ConfigureTemplateRequested) -> None:
        message.stop()
        if message.config is not self._form_config:
            spec = self.resolve(message.config)
            if spec is None:
                return
            self._form_config, self._form_spec = message.config, spec
            slot = self.query_one("#template-form-view")
            await slot.remove_children()
            if spec.fields:
                await slot.mount(TemplateSetupForm(spec))
        spec = self._form_spec
        if spec is None:
            return
        if not spec.fields:
            self.dismiss((message.config, spec, {}))
            return
        self._show_view("form")

    @on(TemplateSetupForm.BackRequested)
    def back_from_form(self, message: TemplateSetupForm.BackRequested) -> None:
        message.stop()
        self.action_back()

    @on(TemplateSetupForm.Submitted)
    def submit_form(self, message: TemplateSetupForm.Submitted) -> None:
        message.stop()
        self.dismiss((self._form_config, self._form_spec, message.values))
