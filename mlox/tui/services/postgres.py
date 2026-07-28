"""Textual database browser for the PostgreSQL service."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from rich.panel import Panel
from rich.table import Table as RichTable
from rich.text import Text
from textual import on
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Button, DataTable, Static, Tree

from mlox.application.use_cases.postgres import (
    DEFAULT_PAGE_SIZE,
    load_postgres_catalog,
    load_postgres_table_page,
)
from mlox.infra import Bundle, Infrastructure
from mlox.services.postgres.docker import PostgresDockerService


class PostgresSettingsPanel(Vertical):
    """Read-only catalog tree and paginated table preview."""

    def __init__(
        self,
        infra: Infrastructure | None,
        bundle: Bundle | None,
        service: PostgresDockerService | Any,
    ) -> None:
        super().__init__(id="postgres-settings")
        self.infra = infra
        self.bundle = bundle
        self.service = service
        self.page = 0
        self.page_size = DEFAULT_PAGE_SIZE
        self.selected_table: dict[str, Any] | None = None
        self._catalog: dict[str, Any] = {"databases": [], "tables": [], "errors": []}
        self._busy = False

    def compose(self) -> ComposeResult:
        with Horizontal(id="postgres-toolbar"):
            yield Button("Refresh Catalog", id="postgres-refresh", variant="primary")
            yield Static("Read-only browser", id="postgres-readonly-label")
        yield Static(id="postgres-summary")
        with Horizontal(id="postgres-browser"):
            tree: Tree[dict[str, Any]] = Tree("PostgreSQL", id="postgres-tree")
            tree.show_root = True
            yield tree
            with Vertical(id="postgres-data-panel"):
                yield Static(
                    "Select a table or view from the catalog.",
                    id="postgres-table-details",
                )
                data_table = DataTable(id="postgres-data-table")
                data_table.cursor_type = "cell"
                data_table.zebra_stripes = True
                yield data_table
                with Horizontal(id="postgres-pagination"):
                    yield Button("Previous", id="postgres-previous")
                    yield Static("Page –", id="postgres-page-label")
                    yield Button("Next", id="postgres-next")
        yield Static(id="postgres-message")

    @property
    def catalog_tree(self) -> Tree:
        return self.query_one("#postgres-tree", Tree)

    @property
    def data_table(self) -> DataTable:
        return self.query_one("#postgres-data-table", DataTable)

    def on_mount(self) -> None:
        self._show_loading("Loading PostgreSQL catalog…")
        self._load_catalog()

    @on(Button.Pressed, "#postgres-refresh")
    def handle_refresh(self, _: Button.Pressed) -> None:
        self._show_loading("Refreshing PostgreSQL catalog…")
        self._load_catalog()

    @on(Tree.NodeSelected, "#postgres-tree")
    def handle_tree_selection(self, event: Tree.NodeSelected) -> None:
        data = event.node.data
        if not isinstance(data, dict) or data.get("kind") not in {
            "table",
            "view",
            "materialized view",
        }:
            if event.node.allow_expand:
                event.node.toggle()
            return
        self.selected_table = data
        self.page = 0
        self._load_page()

    @on(Button.Pressed, "#postgres-previous")
    def handle_previous(self, _: Button.Pressed) -> None:
        if self.selected_table is None or self.page <= 0:
            return
        self.page -= 1
        self._load_page()

    @on(Button.Pressed, "#postgres-next")
    def handle_next(self, _: Button.Pressed) -> None:
        if self.selected_table is None:
            return
        self.page += 1
        self._load_page()

    def _load_catalog(self) -> None:
        self._set_busy(True)
        self._run_operation(
            lambda: load_postgres_catalog(self.service),
            self._apply_catalog,
            group="postgres-catalog",
        )

    def _load_page(self) -> None:
        selected = self.selected_table
        if selected is None:
            return
        self._set_busy(True)
        self.query_one("#postgres-message", Static).update("Loading table rows…")
        self._run_operation(
            lambda: load_postgres_table_page(
                self.service,
                database=str(selected["database"]),
                schema=str(selected["schema"]),
                table=str(selected["name"]),
                page=self.page,
                page_size=self.page_size,
            ),
            self._apply_page,
            group="postgres-table-page",
        )

    def _run_operation(self, operation, callback, *, group: str) -> None:
        app = self.app

        def finish(result) -> None:
            if self.is_attached:
                callback(result)

        def run() -> None:
            app.call_from_thread(finish, operation())

        app.run_worker(run, thread=True, exclusive=True, group=group)

    def _apply_catalog(self, result) -> None:
        self._set_busy(False)
        if not result.success:
            self.query_one("#postgres-summary", Static).update(
                Panel(Text(result.message, style="bold red"), title="PostgreSQL")
            )
            self.query_one("#postgres-message", Static).update(result.message)
            return

        self._catalog = result.data or {"databases": [], "tables": [], "errors": []}
        self._render_summary()
        self._populate_tree()
        errors = self._catalog.get("errors", [])
        message = result.message
        if errors:
            message += f" {len(errors)} database(s) could not be inspected."
        self.query_one("#postgres-message", Static).update(message)

    def _apply_page(self, result) -> None:
        self._set_busy(False)
        if not result.success:
            self.query_one("#postgres-message", Static).update(
                Text(result.message, style="bold red")
            )
            self.query_one("#postgres-next", Button).disabled = True
            return

        payload = result.data or {}
        table = self.data_table
        table.clear(columns=True)
        columns = [str(column) for column in payload.get("columns", [])]
        if columns:
            table.add_columns(*columns)
        for row in payload.get("rows", []):
            table.add_row(*(str(value) for value in row))

        primary_key = payload.get("primary_key", [])
        order_label = (
            f"primary key: {', '.join(primary_key)}"
            if primary_key
            else "no stable ordering"
        )
        column_info = payload.get("column_info", [])
        nullable = sum(1 for column in column_info if column.get("nullable"))
        selected = self.selected_table or {}
        details = (
            f"{payload.get('database')}.{payload.get('schema')}.{payload.get('table')}  •  "
            f"{selected.get('kind', 'table')}  •  {len(columns)} columns "
            f"({nullable} nullable)  •  {order_label}\n"
            f"Estimated rows: ~{int(selected.get('estimated_rows', 0)):,}  •  "
            f"Size: {_format_bytes(int(selected.get('size_bytes', 0)))}  •  "
            f"DML since reset: {int(selected.get('inserts', 0)):,} inserts, "
            f"{int(selected.get('updates', 0)):,} updates, "
            f"{int(selected.get('deletes', 0)):,} deletes"
        )
        self.query_one("#postgres-table-details", Static).update(details)
        self.query_one("#postgres-page-label", Static).update(
            f"Page {int(payload.get('page', 0)) + 1} · {len(payload.get('rows', []))} rows"
        )
        self.query_one("#postgres-previous", Button).disabled = self.page <= 0
        self.query_one("#postgres-next", Button).disabled = not bool(
            payload.get("has_more")
        )
        self.query_one("#postgres-message", Static).update(result.message)

    def _populate_tree(self) -> None:
        tree = self.catalog_tree
        tree.clear()
        root = tree.root
        root.set_label("PostgreSQL")
        tables = self._catalog.get("tables", [])
        by_database: dict[str, list[dict[str, Any]]] = {}
        for item in tables:
            by_database.setdefault(str(item["database"]), []).append(item)

        for database in self._catalog.get("databases", []):
            name = str(database["name"])
            db_node = root.add(
                f"{name}  [{_format_bytes(int(database.get('size_bytes', 0)))}]",
                data={"kind": "database", **database},
            )
            by_schema: dict[str, list[dict[str, Any]]] = {}
            for item in by_database.get(name, []):
                by_schema.setdefault(str(item["schema"]), []).append(item)
            for schema, schema_tables in sorted(by_schema.items()):
                schema_node = db_node.add(
                    f"{schema}  [{len(schema_tables)}]",
                    data={"kind": "schema", "database": name, "schema": schema},
                )
                for item in schema_tables:
                    icon = "▦" if item["kind"] == "table" else "◫"
                    schema_node.add_leaf(
                        f"{icon} {item['name']}  [~{item['estimated_rows']:,}]",
                        data=item,
                    )
            db_node.expand()
        root.expand()

    def _render_summary(self) -> None:
        databases = self._catalog.get("databases", [])
        tables = self._catalog.get("tables", [])
        schemas = {(row["database"], row["schema"]) for row in tables}
        estimated_rows = sum(int(row.get("estimated_rows", 0)) for row in tables)
        size_bytes = sum(int(row.get("size_bytes", 0)) for row in databases)
        dml = sum(
            int(row.get("inserts", 0))
            + int(row.get("updates", 0))
            + int(row.get("deletes", 0))
            for row in tables
        )
        maintenance = [
            row.get("last_maintenance")
            for row in tables
            if row.get("last_maintenance")
        ]

        grid = RichTable.grid(expand=True, padding=(0, 2))
        for _ in range(6):
            grid.add_column(justify="center")
        grid.add_row(
            "Databases",
            "Schemas",
            "Relations",
            "Estimated rows",
            "DML since reset",
            "Size",
        )
        grid.add_row(
            str(len(databases)),
            str(len(schemas)),
            str(len(tables)),
            f"~{estimated_rows:,}",
            f"{dml:,}",
            _format_bytes(size_bytes),
        )
        subtitle = "Last maintenance: " + (
            _format_timestamp(max(maintenance)) if maintenance else "not recorded"
        )
        self.query_one("#postgres-summary", Static).update(
            Panel(grid, title="PostgreSQL", subtitle=subtitle, border_style="green")
        )

    def _show_loading(self, message: str) -> None:
        if list(self.query("#postgres-summary")):
            self.query_one("#postgres-summary", Static).update(
                Panel(Text(message), title="PostgreSQL")
            )

    def _set_busy(self, busy: bool) -> None:
        self._busy = busy
        self.query_one("#postgres-refresh", Button).disabled = busy
        self.query_one("#postgres-previous", Button).disabled = busy or self.page <= 0
        self.query_one("#postgres-next", Button).disabled = (
            busy or self.selected_table is None
        )


def _format_bytes(value: int) -> str:
    size = float(max(0, value))
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if size < 1024 or unit == "TiB":
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} TiB"


def _format_timestamp(value: Any) -> str:
    if isinstance(value, datetime):
        return value.astimezone().isoformat(sep=" ", timespec="seconds")
    return str(value)


def settings(
    infra: Infrastructure,
    bundle: Bundle,
    service: PostgresDockerService,
) -> PostgresSettingsPanel:
    return PostgresSettingsPanel(infra, bundle, service)
