"""Knowledge-base panel: project notes, todos, wiki, FAQ, and boards."""

from __future__ import annotations

from typing import Optional

from rich.text import Text
from textual import on
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import (
    Button,
    DataTable,
    Input,
    Label,
    Markdown,
    Select,
    Static,
    TextArea,
)

from mlox.project.entries import (
    ENTRY_KINDS,
    Entry,
    add_item,
    default_template,
    extract_links,
    find_template_body,
    lane_color,
    linkify_item,
    move_item,
    next_kind,
    parse_board,
    remove_item,
    rewrite_links,
    toggle_item,
)

BOARD_ENTRY_TITLE = "Board"


class NewCardDialog(ModalScreen[Optional[str]]):
    """Prompt for free-form text (new board card or link title)."""

    def __init__(self, heading: str, value: str = "") -> None:
        super().__init__()
        self._heading = heading
        self._value = value

    def compose(self) -> ComposeResult:
        with Vertical(id="kb-dialog"):
            yield Label(self._heading, id="kb-dialog-title")
            yield Input(value=self._value, placeholder="Title", id="kb-card-input")
            with Horizontal(id="kb-dialog-actions"):
                yield Button("Cancel", id="kb-card-cancel")
                yield Button("Confirm", id="kb-card-confirm")

    def on_mount(self) -> None:
        self.query_one("#kb-card-input", Input).focus()

    @on(Input.Submitted, "#kb-card-input")
    def handle_submitted(self, event: Input.Submitted) -> None:
        self.dismiss(event.value.strip() or None)

    @on(Button.Pressed, "#kb-card-cancel")
    def handle_cancel(self, _: Button.Pressed) -> None:
        self.dismiss(None)

    @on(Button.Pressed, "#kb-card-confirm")
    def handle_confirm(self, _: Button.Pressed) -> None:
        self.dismiss(self.query_one("#kb-card-input", Input).value.strip() or None)


class NewEntryDialog(ModalScreen[Optional[tuple[str, str]]]):
    """Prompt for kind and title of a new knowledge-base entry."""

    def compose(self) -> ComposeResult:
        with Vertical(id="kb-dialog"):
            yield Label("New knowledge entry", id="kb-dialog-title")
            yield Select(
                [(kind.title(), kind) for kind in ENTRY_KINDS if kind != "template"],
                id="kb-entry-kind",
                allow_blank=False,
            )
            yield Input(placeholder="Title", id="kb-entry-title-input")
            with Horizontal(id="kb-dialog-actions"):
                yield Button("Cancel", id="kb-entry-cancel")
                yield Button("Create", id="kb-entry-confirm")

    def on_mount(self) -> None:
        self.query_one("#kb-entry-title-input", Input).focus()

    @on(Button.Pressed, "#kb-entry-cancel")
    def handle_cancel(self, _: Button.Pressed) -> None:
        self.dismiss(None)

    @on(Button.Pressed, "#kb-entry-confirm")
    def handle_confirm(self, _: Button.Pressed) -> None:
        self._submit()

    @on(Input.Submitted, "#kb-entry-title-input")
    def handle_submitted(self, _: Input.Submitted) -> None:
        self._submit()

    def _submit(self) -> None:
        title = self.query_one("#kb-entry-title-input", Input).value.strip()
        kind = self.query_one("#kb-entry-kind", Select).value
        if title and kind:
            self.dismiss((str(kind), title))


class ConfirmDeleteDialog(ModalScreen[bool]):
    """Confirmation prompt before deleting an entry."""

    def __init__(self, title: str) -> None:
        super().__init__()
        self._title = title

    def compose(self) -> ComposeResult:
        with Vertical(id="kb-dialog"):
            yield Label("Delete entry", id="kb-dialog-title")
            yield Static(f"Do you really want to delete '{self._title}'?")
            with Horizontal(id="kb-dialog-actions"):
                yield Button("Cancel", id="kb-delete-cancel")
                yield Button("Delete", id="kb-delete-confirm")

    @on(Button.Pressed, "#kb-delete-cancel")
    def handle_cancel(self, _: Button.Pressed) -> None:
        self.dismiss(False)

    @on(Button.Pressed, "#kb-delete-confirm")
    def handle_confirm(self, _: Button.Pressed) -> None:
        self.dismiss(True)


class EditEntryScreen(ModalScreen[Optional[str]]):
    """Raw markdown editor for one entry body."""

    BINDINGS = [("ctrl+s", "save_entry", "Save")]

    def __init__(self, title: str, body: str) -> None:
        super().__init__()
        self._title = title
        self._body = body

    def compose(self) -> ComposeResult:
        with Vertical(id="kb-edit-screen"):
            yield Label(
                f"Edit: {self._title}  (ctrl+s to save)", id="kb-dialog-title"
            )
            yield TextArea(self._body, id="kb-edit-area")
            with Horizontal(id="kb-dialog-actions"):
                yield Button("Cancel", id="kb-edit-cancel")
                yield Button("Save", id="kb-edit-confirm")

    def on_mount(self) -> None:
        self.query_one("#kb-edit-area", TextArea).focus()

    def action_save_entry(self) -> None:
        self.dismiss(self.query_one("#kb-edit-area", TextArea).text)

    @on(Button.Pressed, "#kb-edit-cancel")
    def handle_cancel(self, _: Button.Pressed) -> None:
        self.dismiss(None)

    @on(Button.Pressed, "#kb-edit-confirm")
    def handle_confirm(self, _: Button.Pressed) -> None:
        self.dismiss(self.query_one("#kb-edit-area", TextArea).text)


class KBBoard(Horizontal, can_focus=True):
    """Markdown-driven kanban view: columns are ## headers, cards are checkboxes."""

    BINDINGS = [
        ("up", "cursor_up", "Up"),
        ("down", "cursor_down", "Down"),
        ("left", "column_left", "Prev column"),
        ("right", "column_right", "Next column"),
        Binding("k", "cursor_up", "Up", show=False),
        Binding("j", "cursor_down", "Down", show=False),
        Binding("h", "column_left", "Prev column", show=False),
        Binding("l", "column_right", "Next column", show=False),
        ("space", "toggle_card", "Toggle"),
        ("H", "move_card_left", "Move left"),
        ("L", "move_card_right", "Move right"),
        ("enter", "open_card", "Open"),
        ("n", "new_card", "New card"),
        ("d", "delete_card", "Delete card"),
        ("e", "edit_markdown", "Edit markdown"),
    ]

    def __init__(self, panel: "KnowledgePanel", **kwargs) -> None:
        super().__init__(**kwargs)
        self._panel = panel
        self._columns: list = []
        self._sel_col = 0
        self._sel_item = 0

    @property
    def selection(self) -> Optional[tuple[int, int]]:
        if not self._columns:
            return None
        self._sel_col = min(self._sel_col, len(self._columns) - 1)
        column = self._columns[self._sel_col]
        if not column.items:
            return (self._sel_col, 0)
        self._sel_item = min(self._sel_item, len(column.items) - 1)
        return (self._sel_col, self._sel_item)

    def show_body(self, body: str) -> None:
        self._columns = parse_board(body)
        self._sel_col = min(self._sel_col, max(len(self._columns) - 1, 0))
        self._refresh()

    def _refresh(self) -> None:
        self.remove_children()
        widgets = []
        for col_idx, column in enumerate(self._columns):
            color = lane_color(column.name)
            text = Text()
            if not column.items:
                text.append("(empty)", style="dim italic")
            for item_idx, item in enumerate(column.items):
                marker = "✓ " if item.checked else "· "
                selected = (col_idx, item_idx) == self.selection
                if selected:
                    style = f"black bold on {color}"
                else:
                    style = "dim" if item.checked else ""
                text.append(marker + item.text + "\n", style=style)
            widget = Static(text, classes="kb-column")
            widget.border_title = Text(column.name, style=f"bold {color}")
            widget.styles.border = ("round", color)
            widgets.append(widget)
        if widgets:
            self.mount(*widgets)

    # --- navigation -------------------------------------------------

    def action_cursor_up(self) -> None:
        self._sel_item = max(self._sel_item - 1, 0)
        self._refresh()

    def action_cursor_down(self) -> None:
        self._sel_item += 1
        self._refresh()

    def action_column_left(self) -> None:
        if self._sel_col > 0:
            self._sel_col -= 1
            self._sel_item = 0
            self._refresh()

    def action_column_right(self) -> None:
        if self._sel_col < len(self._columns) - 1:
            self._sel_col += 1
            self._sel_item = 0
            self._refresh()

    # --- mutations (delegated to the panel) -------------------------

    def action_toggle_card(self) -> None:
        selection = self.selection
        if selection:
            self._panel.toggle_card(*selection)

    def action_move_card_left(self) -> None:
        selection = self.selection
        if selection:
            self._panel.move_card(selection[0], selection[1], -1)

    def action_move_card_right(self) -> None:
        selection = self.selection
        if selection:
            self._panel.move_card(selection[0], selection[1], 1)

    def action_open_card(self) -> None:
        selection = self.selection
        if selection:
            self._panel.open_card(*selection)

    def action_new_card(self) -> None:
        self._panel.new_card(self._sel_col)

    def action_delete_card(self) -> None:
        selection = self.selection
        if selection:
            self._panel.delete_card(*selection)

    def action_edit_markdown(self) -> None:
        self._panel.edit_board_markdown()


class KnowledgePanel(Container):
    """Project knowledge base: entry list with a type-aware viewer."""

    BINDINGS = [Binding("space", "cycle_kind", "Change type")]

    def compose(self) -> ComposeResult:
        yield Input(placeholder="Search knowledge base…", id="kb-search")
        with Horizontal(id="kb-entry-actions"):
            yield Button("New", id="kb-new-entry")
            yield Button("Edit", id="kb-edit-entry")
            yield Button("Rename", id="kb-rename-entry")
            yield Button("Delete", id="kb-delete-entry")
            yield Static("", id="kb-actions-spacer")
            yield Button("New Card", id="kb-new-card")
        with Horizontal(id="kb-entries-layout"):
            yield DataTable(id="kb-entry-table")
            with Vertical(id="kb-viewer"):
                with VerticalScroll(id="kb-viewer-scroll"):
                    yield Markdown(id="kb-viewer-markdown")
                yield KBBoard(self, id="kb-board")
                yield Static("", id="kb-backlinks")
        yield Static(
            "space: change type · board: h/j/k/l or arrows move · space: toggle "
            "card · H/L: move card · enter: open/link · n: new · d: delete · "
            "e: edit raw",
            id="kb-help",
        )
        yield Static("", id="kb-status")

    # ------------------------------------------------------------------
    # Data access
    # ------------------------------------------------------------------

    @property
    def board(self) -> KBBoard:
        return self.query_one("#kb-board", KBBoard)

    @property
    def table(self) -> DataTable:
        return self.query_one("#kb-entry-table", DataTable)

    @property
    def status(self) -> Static:
        return self.query_one("#kb-status", Static)

    @property
    def viewer(self) -> Markdown:
        return self.query_one("#kb-viewer-markdown", Markdown)

    def _workspace(self):
        return getattr(self.app, "workspace", None)

    def on_mount(self) -> None:
        self.table.add_columns("Kind", "Title")
        self.query_one("#kb-new-card").display = False
        self.board.display = False
        self.reload_entries()

    def reload_entries(self) -> None:
        workspace = self._workspace()
        list_entries = getattr(workspace, "list_entries", None)
        if not callable(list_entries):
            self._entries: list[Entry] = []
            self.status.update("Knowledge base requires a project workspace.")
            return
        self._entries = list(list_entries())
        if not self._entries:
            save_entry = getattr(workspace, "save_entry", None)
            if callable(save_entry):
                seeded = save_entry(
                    Entry(
                        kind="board",
                        title=BOARD_ENTRY_TITLE,
                        body_md=default_template("board", BOARD_ENTRY_TITLE),
                    )
                )
                self._entries = [seeded]
        self._refresh_table()
        self._show_entry(self._first_board())

    def _first_board(self) -> Optional[Entry]:
        boards = [entry for entry in self._entries if entry.kind == "board"]
        return boards[0] if boards else None

    def _entry_by_id(self, entry_id: Optional[str]) -> Optional[Entry]:
        if not entry_id:
            return None
        for entry in self._entries:
            if entry.id == entry_id:
                return entry
        return None

    def _refresh_table(self) -> None:
        table = self.table
        table.clear(columns=False)
        self._row_index: dict[str, int] = {}
        query = self.query_one("#kb-search", Input).value.strip().casefold()
        for entry in self._entries:
            if query and not (
                query in entry.title.casefold() or query in entry.body_md.casefold()
            ):
                continue
            self._row_index[entry.id] = table.row_count
            table.add_row(entry.kind, entry.title, key=entry.id)
        self.status.update(f"{len(self._entries)} entries in project knowledge base.")

    def _select_table_row(self, entry_id: str) -> None:
        row_idx = getattr(self, "_row_index", {}).get(entry_id)
        if row_idx is not None:
            self.table.cursor_coordinate = (row_idx, 0)

    def _current_entry(self) -> Optional[Entry]:
        """Selected entry, falling back to the row under the table cursor."""
        entry = self._entry_by_id(self._selected_entry_id)
        if entry is not None:
            return entry
        table = self.table
        try:
            row_key = table.coordinate_to_cell_key(table.cursor_coordinate).row_key
        except Exception:
            return None
        return self._entry_by_id(str(row_key.value or ""))

    # ------------------------------------------------------------------
    # Entry display (type-aware right-hand side)
    # ------------------------------------------------------------------

    def _show_entry(self, entry: Optional[Entry]) -> None:
        if entry is None:
            self.board.display = False
            self.query_one("#kb-viewer-scroll").display = False
            self.query_one("#kb-backlinks").display = False
            self.query_one("#kb-new-card").display = False
            self.viewer.update("")
            self.query_one("#kb-backlinks", Static).update("")
            return
        self._selected_entry_id = entry.id
        is_board = entry.kind == "board"
        self.query_one("#kb-new-card").display = is_board
        self.board.display = is_board
        self.query_one("#kb-viewer-scroll").display = not is_board
        self.query_one("#kb-backlinks").display = not is_board
        if is_board:
            self._load_board(entry)
        else:
            self.viewer.update(entry.body_md)
            self._update_backlinks(entry)

    def _update_backlinks(self, entry: Entry) -> None:
        wanted = entry.title.strip().casefold()
        backlinks = []
        for other in self._entries:
            if other.id == entry.id:
                continue
            for target in extract_links(other.body_md):
                if target.strip().casefold() == wanted:
                    backlinks.append(other.title)
                    break
        self.query_one("#kb-backlinks", Static).update(
            "Referenced by: " + ", ".join(backlinks) if backlinks else ""
        )

    def open_entry_by_title(self, title: str) -> None:
        workspace = self._workspace()
        find = getattr(workspace, "find_entry_by_title", None)
        entry = find(title) if callable(find) else None
        if entry is None:
            self.app.notify(f"No entry titled '{title}'.", severity="warning")
            return
        self._show_entry(entry)
        self._select_table_row(entry.id)

    # ------------------------------------------------------------------
    # Type cycling
    # ------------------------------------------------------------------

    def action_cycle_kind(self) -> None:
        entry = self._current_entry()
        if entry is None:
            self.app.notify("Select an entry first.", severity="warning")
            return
        entry.kind = next_kind(entry.kind)
        if entry.kind == "board":
            has_content = any(
                line.strip() and not line.lstrip().startswith("#")
                for line in entry.body_md.splitlines()
            )
            if not has_content:
                # Bare template stub: start a real board layout.
                entry.body_md = default_template("board", entry.title)
            elif not parse_board(entry.body_md):
                # Real content without lanes: keep it, add the lanes below.
                entry.body_md = (
                    entry.body_md.rstrip() + "\n\n" + default_template("board", entry.title)
                )
        self._workspace().save_entry(entry)
        self._entries = list(self._workspace().list_entries())
        self._refresh_table()
        self._show_entry(entry)
        self._select_table_row(entry.id)
        self.app.notify(f"Type: {entry.kind}")

    # ------------------------------------------------------------------
    # Board handling
    # ------------------------------------------------------------------

    def _load_board(self, entry: Optional[Entry]) -> None:
        self._board_entry = entry
        self.board.show_body(entry.body_md if entry else "")

    def _save_board_body(self, body: str) -> None:
        workspace = self._workspace()
        if self._board_entry is None or not callable(
            getattr(workspace, "save_entry", None)
        ):
            return
        self._board_entry.body_md = body
        workspace.save_entry(self._board_entry)
        self.board.show_body(body)

    def toggle_card(self, col_idx: int, item_idx: int) -> None:
        if self._board_entry is None:
            return
        columns = parse_board(self._board_entry.body_md)
        item = columns[col_idx].items[item_idx]
        self._save_board_body(toggle_item(self._board_entry.body_md, item.line_no))

    def move_card(self, col_idx: int, item_idx: int, offset: int) -> None:
        if self._board_entry is None:
            return
        columns = parse_board(self._board_entry.body_md)
        item = columns[col_idx].items[item_idx]
        target_idx = col_idx + offset
        if not (0 <= target_idx < len(columns)):
            return
        body = move_item(self._board_entry.body_md, col_idx, item_idx, offset)
        self._save_board_body(body)
        for new_idx, moved in enumerate(columns[target_idx].items):
            if moved.text == item.text:
                self.board._sel_col = target_idx
                self.board._sel_item = new_idx
                self.board._refresh()
                return

    def delete_card(self, col_idx: int, item_idx: int) -> None:
        if self._board_entry is None:
            return
        self._save_board_body(
            remove_item(self._board_entry.body_md, col_idx, item_idx)
        )

    def new_card(self, col_idx: int) -> None:
        if self._board_entry is None:
            return
        columns = parse_board(self._board_entry.body_md)
        column_name = columns[col_idx].name if col_idx < len(columns) else ""
        self.app.push_screen(
            NewCardDialog(f"New card in '{column_name}'"),
            lambda text: text and self._add_card(col_idx, text),
        )

    def _add_card(self, col_idx: int, text: str) -> None:
        if self._board_entry is None:
            return
        self._save_board_body(add_item(self._board_entry.body_md, col_idx, text))

    def open_card(self, col_idx: int, item_idx: int) -> None:
        if self._board_entry is None:
            return
        columns = parse_board(self._board_entry.body_md)
        item = columns[col_idx].items[item_idx]
        if item.links:
            self.open_entry_by_title(item.links[0])
            return
        self.app.push_screen(
            NewCardDialog("Link card to entry (creates a todo if missing)"),
            lambda title: title and self._linkify_card(col_idx, item_idx, title),
        )

    def _linkify_card(self, col_idx: int, item_idx: int, title: str) -> None:
        if self._board_entry is None:
            return
        columns = parse_board(self._board_entry.body_md)
        item = columns[col_idx].items[item_idx]
        workspace = self._workspace()
        find = getattr(workspace, "find_entry_by_title", None)
        entry = find(title) if callable(find) else None
        if entry is None:
            entry = self._create_entry("todo", title)
        self._save_board_body(
            linkify_item(self._board_entry.body_md, item.line_no, entry.title)
        )

    def edit_board_markdown(self) -> None:
        if self._board_entry is None:
            return
        self.app.push_screen(
            EditEntryScreen(self._board_entry.title, self._board_entry.body_md),
            lambda body: body is not None and self._save_board_body(body),
        )

    # ------------------------------------------------------------------
    # Entry handling
    # ------------------------------------------------------------------

    def _create_entry(self, kind: str, title: str) -> Entry:
        workspace = self._workspace()
        templates = [entry for entry in self._entries if entry.kind == "template"]
        body = find_template_body(templates, kind) or default_template(kind, title)
        entry = workspace.save_entry(Entry(kind=kind, title=title, body_md=body))
        self._entries = list(workspace.list_entries())
        self._refresh_table()
        return entry

    def _create_and_show(self, kind: str, title: str) -> None:
        entry = self._create_entry(kind, title)
        self._refresh_table()
        self._show_entry(entry)
        self._select_table_row(entry.id)

    @on(DataTable.RowSelected, "#kb-entry-table")
    def handle_row_selected(self, event: DataTable.RowSelected) -> None:
        entry = self._entry_by_id(str(event.row_key.value or ""))
        if entry is not None:
            self._show_entry(entry)

    @on(DataTable.CellHighlighted, "#kb-entry-table")
    def handle_cell_highlighted(self, event: DataTable.CellHighlighted) -> None:
        try:
            row_key = self.table.coordinate_to_cell_key(event.coordinate).row_key
        except Exception:
            return
        entry = self._entry_by_id(str(row_key.value or ""))
        if entry is not None:
            self._show_entry(entry)

    @on(Input.Changed, "#kb-search")
    def handle_search_changed(self, _: Input.Changed) -> None:
        self._refresh_table()

    @on(Button.Pressed, "#kb-new-entry")
    def handle_new_entry(self, _: Button.Pressed) -> None:
        self.app.push_screen(
            NewEntryDialog(),
            lambda result: result and self._create_and_show(*result),
        )

    @on(Button.Pressed, "#kb-edit-entry")
    def handle_edit_entry(self, _: Button.Pressed) -> None:
        entry = self._current_entry()
        if entry is None:
            self.app.notify("Select an entry first.", severity="warning")
            return
        self.app.push_screen(
            EditEntryScreen(entry.title, entry.body_md),
            lambda body: body is not None and self._save_entry_body(entry, body),
        )

    def _save_entry_body(self, entry: Entry, body: str) -> None:
        workspace = self._workspace()
        entry.body_md = body
        workspace.save_entry(entry)
        self._entries = list(workspace.list_entries())
        self._refresh_table()
        self._show_entry(entry)

    @on(Button.Pressed, "#kb-rename-entry")
    def handle_rename_entry(self, _: Button.Pressed) -> None:
        entry = self._current_entry()
        if entry is None:
            self.app.notify("Select an entry first.", severity="warning")
            return
        self.app.push_screen(
            NewCardDialog(f"Rename '{entry.title}'"),
            lambda title: title and self._apply_rename(entry, title),
        )

    def _apply_rename(self, entry: Entry, new_title: str) -> None:
        workspace = self._workspace()
        old_title = entry.title
        for other in self._entries:
            if other.id == entry.id or "[[" not in other.body_md:
                continue
            rewritten = rewrite_links(other.body_md, old_title, new_title)
            if rewritten != other.body_md:
                other.body_md = rewritten
                workspace.save_entry(other)
        entry.title = new_title
        workspace.save_entry(entry)
        self._entries = list(workspace.list_entries())
        self._refresh_table()
        self._show_entry(entry)
        self._select_table_row(entry.id)
        self.app.notify(f"Renamed to '{new_title}' (links updated).")

    @on(Button.Pressed, "#kb-delete-entry")
    def handle_delete_entry(self, _: Button.Pressed) -> None:
        entry = self._current_entry()
        if entry is None:
            self.app.notify("Select an entry first.", severity="warning")
            return
        self.app.push_screen(
            ConfirmDeleteDialog(entry.title),
            lambda confirm: confirm and self._delete_entry(entry),
        )

    def _delete_entry(self, entry: Entry) -> None:
        self._workspace().delete_entry(entry.id)
        self._selected_entry_id = None
        self._show_entry(None)
        self.reload_entries()

    @on(Button.Pressed, "#kb-new-card")
    def handle_new_card(self, _: Button.Pressed) -> None:
        self.board.action_new_card()
