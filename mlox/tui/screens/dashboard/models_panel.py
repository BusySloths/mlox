"""Project model operations browser."""

from __future__ import annotations

from typing import Any, Optional

from rich.text import Text
from textual import on
from textual.app import ComposeResult
from textual.containers import Container, Horizontal, Vertical
from textual.reactive import reactive
from textual.screen import ModalScreen
from textual.widgets import Button, DataTable, Label, Static, TextArea

from mlox.application.use_cases.models import (
    build_model_example,
    call_model_example,
    describe_model_operations,
)

from .model import SelectionInfo


class ModelCallResultDialog(ModalScreen[None]):
    """Modal result viewer for a model invocation."""

    def __init__(self, title: str, body: str) -> None:
        super().__init__()
        self.title = title
        self.body = body

    def compose(self) -> ComposeResult:
        with Container(id="model-call-result-dialog"):
            yield Label(self.title, id="model-call-result-title")
            yield TextArea(self.body, id="model-call-result-body")
            with Horizontal(id="model-call-result-actions"):
                yield Button("Close", id="close-model-call-result")

    @on(Button.Pressed, "#close-model-call-result")
    def handle_close(self, _: Button.Pressed) -> None:
        self.dismiss(None)


class ModelsPanel(Static):
    """Registry, endpoint, model, and invocation example overview."""

    selection: reactive[Optional[SelectionInfo]] = reactive(None)

    def __init__(self, *children, **kwargs) -> None:
        super().__init__(*children, **kwargs)
        self._registries: list[dict[str, Any]] = []
        self._endpoints: list[dict[str, Any]] = []
        self._models_by_endpoint: dict[str, list[dict[str, Any]]] = {}
        self._example_cache: dict[tuple[str, str], str] = {}
        self._registry_ids: list[str] = []
        self._endpoint_ids: list[str] = []
        self._model_ids: list[str] = []
        self._selected_registry_id = ""
        self._selected_endpoint_id = ""
        self._selected_model_id = ""
        self._example_request_id = 0

    def compose(self) -> ComposeResult:
        with Vertical(id="models-content"):
            with Horizontal(id="models-metrics"):
                yield Static(id="models-metric-registries", classes="model-metric")
                yield Static(id="models-metric-endpoints", classes="model-metric")
                yield Static(id="models-metric-total", classes="model-metric")
                yield Static(id="models-metric-available", classes="model-metric")
            with Horizontal(id="models-browser"):
                registry_table = DataTable(id="model-registry-table")
                registry_table.cursor_type = "row"
                registry_table.add_columns("Registry", "Status")
                yield registry_table

                endpoint_table = DataTable(id="model-endpoint-table")
                endpoint_table.cursor_type = "row"
                endpoint_table.add_columns("Endpoint", "Bundle", "Status")
                yield endpoint_table

                model_table = DataTable(id="served-model-table")
                model_table.cursor_type = "row"
                model_table.add_columns("Model", "Version", "Type", "Status")
                yield model_table
            with Horizontal(id="model-example-actions"):
                yield Static("Serving Example", id="model-example-title")
                yield Button("Load Curl Example", id="load-model-example")
                yield Button("Call Model", id="call-model-example")
                yield Button("Copy Curl Example", id="copy-model-example")
            yield TextArea("", id="model-example")

    @property
    def registry_table(self) -> DataTable:
        return self.query_one("#model-registry-table", DataTable)

    @property
    def endpoint_table(self) -> DataTable:
        return self.query_one("#model-endpoint-table", DataTable)

    @property
    def model_table(self) -> DataTable:
        return self.query_one("#served-model-table", DataTable)

    @property
    def example(self) -> TextArea:
        return self.query_one("#model-example", TextArea)

    def on_mount(self) -> None:
        self.example.border_title = "Serving Example"
        self.watch_selection(self.selection)

    def watch_selection(self, selection: Optional[SelectionInfo]) -> None:
        if not self.is_mounted:
            return
        if not selection or selection.type != "root":
            self.display = False
            return
        self.display = True
        self.load()

    def load(self) -> None:
        workspace = getattr(self.app, "workspace", None)
        infra = getattr(workspace, "infrastructure", None)
        self._clear_tables()
        self._update_metrics(None)

        def load_models() -> None:
            result = describe_model_operations(infra)
            self.app.call_from_thread(self._show_result, result)

        self.app.run_worker(
            load_models,
            thread=True,
            exclusive=True,
            group="models",
        )

    def _show_result(self, result) -> None:
        if not self.selection or self.selection.type != "root":
            return
        if not result.success:
            self._update_metrics(None, result.message)
            return
        payload = result.data or {}
        self._registries = list(payload.get("registries", []))
        self._endpoints = list(payload.get("endpoints", []))
        self._models_by_endpoint = dict(payload.get("models_by_endpoint", {}))
        self._example_cache = {}
        self._populate_registries()
        self._update_metrics(self._model_metrics())
        if self._registry_ids:
            self._select_registry(self._registry_ids[0])
        else:
            self.example.text = "No model registries or endpoints detected."

    def _clear_tables(self) -> None:
        self.registry_table.clear(columns=False)
        self.endpoint_table.clear(columns=False)
        self.model_table.clear(columns=False)
        self.example.text = ""
        self._registry_ids = []
        self._endpoint_ids = []
        self._model_ids = []
        self._selected_endpoint_id = ""
        self._selected_model_id = ""

    def _populate_registries(self) -> None:
        table = self.registry_table
        table.clear(columns=False)
        self._registry_ids = []
        for registry in self._registries:
            registry_id = str(registry.get("id") or "")
            if not registry_id:
                continue
            self._registry_ids.append(registry_id)
            table.add_row(
                str(registry.get("name", "-")),
                str(registry.get("status", "-")),
                key=registry_id,
            )
        if self._registry_ids:
            table.cursor_coordinate = (0, 0)

    @on(DataTable.RowSelected, "#model-registry-table")
    def handle_registry_selected(self, event: DataTable.RowSelected) -> None:
        self._select_registry(self._row_key(event))

    @on(DataTable.RowSelected, "#model-endpoint-table")
    def handle_endpoint_selected(self, event: DataTable.RowSelected) -> None:
        self._select_endpoint(self._row_key(event))

    @on(DataTable.RowSelected, "#served-model-table")
    def handle_model_selected(self, event: DataTable.RowSelected) -> None:
        self._select_model(self._row_key(event))

    @on(Button.Pressed, "#load-model-example")
    def handle_load_example(self, _: Button.Pressed) -> None:
        self.load_current_example()

    @on(Button.Pressed, "#copy-model-example")
    def handle_copy_example(self, _: Button.Pressed) -> None:
        self.copy_current_example()

    @on(Button.Pressed, "#call-model-example")
    def handle_call_model(self, _: Button.Pressed) -> None:
        self.call_current_example()

    def copy_current_example(self) -> bool:
        example = self.example.text.strip()
        if not example or not example.startswith("curl"):
            self.app.notify("No curl example is available to copy.", severity="warning")
            return False
        self.app.copy_to_clipboard(example)
        self.app.notify("Curl example copied.")
        return True

    def load_current_example(self) -> bool:
        if not self._selected_endpoint_id:
            self.app.notify("Select an endpoint first.", severity="warning")
            return False
        self._load_example(self._selected_endpoint_id, self._selected_model_id)
        return True

    def call_current_example(self) -> bool:
        example = self.example.text.strip()
        if not example or not example.startswith("curl"):
            self.app.notify("Load a curl example before calling the model.", severity="warning")
            return False
        self.example.text = "Calling model..."
        self._example_request_id += 1
        request_id = self._example_request_id

        def call_model() -> None:
            result = call_model_example(example)
            self.app.call_from_thread(self._show_call_result, request_id, example, result)

        self.app.run_worker(
            call_model,
            thread=True,
            exclusive=True,
            group="model-call",
        )
        return True

    def _select_registry(self, registry_id: str) -> None:
        self._selected_registry_id = registry_id
        endpoints = [
            endpoint
            for endpoint in self._endpoints
            if str(endpoint.get("registry_id")) == registry_id
        ]
        self._populate_endpoints(endpoints)
        if self._endpoint_ids:
            self._select_endpoint(self._endpoint_ids[0])
        else:
            self.model_table.clear(columns=False)
            self.example.text = "No endpoints are connected to this registry."

    def _populate_endpoints(self, endpoints: list[dict[str, Any]]) -> None:
        table = self.endpoint_table
        table.clear(columns=False)
        self._endpoint_ids = []
        for endpoint in endpoints:
            endpoint_id = str(endpoint.get("id") or "")
            if not endpoint_id:
                continue
            self._endpoint_ids.append(endpoint_id)
            table.add_row(
                str(endpoint.get("name", "-")),
                str(endpoint.get("bundle", "-")),
                self._state_badge(str(endpoint.get("status", "unknown"))),
                key=endpoint_id,
            )
        if self._endpoint_ids:
            table.cursor_coordinate = (0, 0)

    def _select_endpoint(self, endpoint_id: str) -> None:
        self._selected_endpoint_id = endpoint_id
        models = self._models_by_endpoint.get(endpoint_id, [])
        self._populate_models(models)
        if self._model_ids:
            self._select_model(self._model_ids[0])
        else:
            self._selected_model_id = ""
            self._show_example_prompt(endpoint_id, "")

    def _populate_models(self, models: list[dict[str, Any]]) -> None:
        table = self.model_table
        table.clear(columns=False)
        self._model_ids = []
        for index, model in enumerate(models):
            model_id = str(index)
            self._model_ids.append(model_id)
            table.add_row(
                str(model.get("name", "-")),
                str(model.get("version", "-")),
                str(model.get("type", "-")),
                str(model.get("status", "-")),
                key=model_id,
            )
        if models:
            table.cursor_coordinate = (0, 0)

    def _select_model(self, model_id: str) -> None:
        self._selected_model_id = model_id
        self._show_example_prompt(self._selected_endpoint_id, model_id)

    def _show_example_prompt(self, endpoint_id: str, model_id: str) -> None:
        cached = self._example_cache.get((endpoint_id, model_id))
        if cached is not None:
            self.example.text = cached
            return
        self.example.text = "Press Load Curl Example to build the serving example."

    def _load_example(self, endpoint_id: str, model_id: str) -> None:
        if not endpoint_id:
            self.example.text = "Select an endpoint to load a serving example."
            return
        cache_key = (endpoint_id, model_id)
        cached = self._example_cache.get(cache_key)
        if cached is not None:
            self.example.text = cached
            return
        endpoint = self._endpoint_by_id(endpoint_id)
        if not endpoint:
            self.example.text = "No invocation example is available."
            return
        model = self._model_by_id(endpoint_id, model_id)
        self._example_request_id += 1
        request_id = self._example_request_id
        self.example.text = "Loading serving example..."
        self.set_timer(12, lambda: self._timeout_example(request_id))

        def load_example() -> None:
            result = build_model_example(endpoint, model)
            self.app.call_from_thread(
                self._show_example_result,
                request_id,
                cache_key,
                result,
            )

        self.app.run_worker(
            load_example,
            thread=True,
            exclusive=True,
            group="model-example",
        )

    def _timeout_example(self, request_id: int) -> None:
        if request_id != self._example_request_id:
            return
        if self.example.text == "Loading serving example...":
            self._example_request_id += 1
            self.example.text = (
                "Loading the serving example timed out. "
                "Check the model artifact or try again."
            )

    def _show_example_result(
        self,
        request_id: int,
        cache_key: tuple[str, str],
        result,
    ) -> None:
        if request_id != self._example_request_id:
            return
        if not result.success:
            self.example.text = result.message
            return
        example = str((result.data or {}).get("example") or "")
        self._example_cache[cache_key] = example
        self.example.text = example or "No invocation example is available."

    def _show_call_result(self, request_id: int, example: str, result) -> None:
        if request_id != self._example_request_id:
            return
        self.example.text = example
        body = str((result.data or {}).get("body") or result.message)
        title = "Model Response" if result.success else "Model Call Failed"
        self.app.push_screen(ModelCallResultDialog(title, body))

    def _endpoint_by_id(self, endpoint_id: str) -> dict[str, Any] | None:
        return next(
            (endpoint for endpoint in self._endpoints if str(endpoint.get("id")) == endpoint_id),
            None,
        )

    def _model_by_id(
        self,
        endpoint_id: str,
        model_id: str,
    ) -> dict[str, Any] | None:
        if not model_id:
            return None
        models = self._models_by_endpoint.get(endpoint_id, [])
        try:
            return models[int(model_id)]
        except (ValueError, IndexError):
            return None

    def _model_metrics(self) -> dict[str, int]:
        models = [
            model
            for endpoint_models in self._models_by_endpoint.values()
            for model in endpoint_models
        ]
        return {
            "registries": len(self._registries),
            "endpoints": len(self._endpoints),
            "total": len(models),
            "available": sum(1 for model in models if self._model_is_available(model)),
        }

    def _update_metrics(
        self,
        metrics: dict[str, int] | None,
        message: str = "Loading...",
    ) -> None:
        values = metrics or {
            "registries": 0,
            "endpoints": 0,
            "total": 0,
            "available": 0,
        }
        labels = [
            ("#models-metric-registries", "Registries", values["registries"], "cyan"),
            ("#models-metric-endpoints", "Endpoints", values["endpoints"], "green"),
            ("#models-metric-total", "Models Total", values["total"], "bright_blue"),
            (
                "#models-metric-available",
                "Models Available",
                values["available"],
                "bright_green",
            ),
        ]
        for selector, label, value, color in labels:
            text = Text()
            text.append(f"{value}\n", style=f"bold {color}")
            text.append(label, style="dim")
            self.query_one(selector, Static).update(text)
        if metrics is None:
            self.example.text = message

    def _model_is_available(self, model: dict[str, Any]) -> bool:
        status = str(model.get("status", "")).strip().lower()
        return status in {"available", "ready", "running", "deployed", "production"}

    def _state_badge(self, state: str) -> Text:
        style = {
            "running": "bold white on dark_green",
            "stopped": "bold white on dark_red",
            "un-initialized": "bold black on bright_yellow",
            "unknown": "bold white on grey23",
        }.get(state, "bold white on dark_blue")
        return Text(f" {state} ", style=style)

    def _row_key(self, event: DataTable.RowSelected) -> str:
        row_key = getattr(event.row_key, "value", event.row_key)
        return str(row_key)
