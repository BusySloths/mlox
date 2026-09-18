"""Knowledge-base panel tests."""

from __future__ import annotations

import asyncio
import time
from types import SimpleNamespace

from textual.app import App, ComposeResult
from textual.widgets import Button, DataTable, Markdown, Static

from mlox.project import ProjectWorkspace
from mlox.project.entries import parse_board
from mlox.tui.screens.dashboard.knowledge_panel import (
    KnowledgePanel,
    NewCardDialog,
    NewEntryDialog,
)
from mlox.tui.screens.dashboard.screen import DashboardScreen, KNOWLEDGE_TAB_ID
from mlox.tui.screens.dashboard.screen import (
    OVERVIEW_TAB_ID,
)


class DashboardTestApp(App):
    """Dashboard shell with a real (plaintext-sqlite) workspace."""

    def __init__(self, workspace: ProjectWorkspace) -> None:
        super().__init__()
        self.workspace = workspace

    def compose(self) -> ComposeResult:
        yield DashboardScreen()


def _make_workspace(tmp_path) -> ProjectWorkspace:
    return ProjectWorkspace.create(str(tmp_path / "kb-demo"), "pw")


async def _knowledge_panel(app) -> KnowledgePanel:
    panel = app.query_one(KnowledgePanel)
    app.query_one("#main-tabs", object)
    return panel


async def _wait_until(predicate, what: str, pilot) -> None:
    deadline = time.monotonic() + 2
    while not predicate():
        if time.monotonic() > deadline:
            raise AssertionError(f"Timed out waiting for {what}.")
        await pilot.pause(0.05)


def test_knowledge_panel_seeds_default_board(tmp_path) -> None:
    workspace = _make_workspace(tmp_path)
    app = DashboardTestApp(workspace)

    async def run():
        async with app.run_test() as pilot:
            panel = app.query_one(KnowledgePanel)
            await _wait_until(lambda: panel.board._columns, "seeded board", pilot)
            assert [c.name for c in panel.board._columns] == ["Open", "Doing", "Done"]
            assert workspace.list_entries()[0].kind == "board"
            assert panel.table.row_count == 1

    asyncio.run(run())


def test_knowledge_panel_survives_workspace_without_entries_api(tmp_path) -> None:
    app = DashboardTestApp(SimpleNamespace(name="x"))

    async def run():
        async with app.run_test() as pilot:
            await pilot.pause()
            panel = app.query_one(KnowledgePanel)
            assert panel._entries == []
            text = str(panel.status.renderable if hasattr(panel.status, "renderable") else panel.status.content)
            assert "requires a project workspace" in text

    asyncio.run(run())


def test_new_entry_dialog_creates_entry_with_template(tmp_path) -> None:
    workspace = _make_workspace(tmp_path)
    app = DashboardTestApp(workspace)

    async def run():
        async with app.run_test() as pilot:
            panel = app.query_one(KnowledgePanel)
            await _wait_until(lambda: panel.table.row_count == 1, "seed", pilot)
            panel._open_created_entry("note", "Design decisions")
            await pilot.pause()
            created = workspace.find_entry_by_title("Design decisions")
            assert created is not None
            assert created.kind == "note"
            assert created.body_md.startswith("## Notes")
            assert panel._selected_entry_id == created.id

    asyncio.run(run())


def test_board_card_move_updates_board_body(tmp_path) -> None:
    workspace = _make_workspace(tmp_path)
    app = DashboardTestApp(workspace)

    async def run():
        async with app.run_test() as pilot:
            panel = app.query_one(KnowledgePanel)
            await _wait_until(lambda: panel.board._columns, "seed", pilot)
            board_entry = workspace.find_entry_by_title("Board")
            body = panel.board.show_body.__doc__  # placeholder to silence linters
            panel._add_card(0, "first task")
            panel._add_card(0, "second task")
            await pilot.pause()
            panel.move_card(0, 0, 1)
            await pilot.pause()
            body = workspace.get_entry(board_entry.id).body_md
            columns = parse_board(body)
            assert [i.text for i in columns[0].items] == ["second task"]
            assert [i.text for i in columns[1].items] == ["first task"]

    asyncio.run(run())


def test_board_toggle_and_linkify(tmp_path) -> None:
    workspace = _make_workspace(tmp_path)
    app = DashboardTestApp(workspace)

    async def run():
        async with app.run_test() as pilot:
            panel = app.query_one(KnowledgePanel)
            await _wait_until(lambda: panel.board._columns, "seed", pilot)
            panel._add_card(0, "plain card")
            await pilot.pause()
            board_entry = workspace.find_entry_by_title("Board")
            panel.toggle_card(0, 0)
            await pilot.pause()
            columns = parse_board(workspace.get_entry(board_entry.id).body_md)
            assert columns[0].items[0].checked is True
            panel._linkify_card(0, 0, "My linked todo")
            await pilot.pause()
            columns = parse_board(workspace.get_entry(board_entry.id).body_md)
            assert columns[0].items[0].text == "[[My linked todo]]"
            todo = workspace.find_entry_by_title("My linked todo")
            assert todo is not None and todo.kind == "todo"

    asyncio.run(run())


def test_rename_rewrites_links(tmp_path) -> None:
    workspace = _make_workspace(tmp_path)
    app = DashboardTestApp(workspace)

    async def run():
        async with app.run_test() as pilot:
            panel = app.query_one(KnowledgePanel)
            await _wait_until(lambda: panel.table.row_count == 1, "seed", pilot)
            todo = panel._create_entry("todo", "Old name")
            board_entry = workspace.find_entry_by_title("Board")
            from mlox.project.entries import add_item

            board_entry.body_md = add_item(board_entry.body_md, 0, "[[Old name]]")
            workspace.save_entry(board_entry)
            panel.reload_entries()
            await pilot.pause()

            panel._selected_entry_id = todo.id
            panel._apply_rename(todo, "New name")
            await pilot.pause()

            columns = parse_board(workspace.get_entry(board_entry.id).body_md)
            assert columns[0].items[0].text == "[[New name]]"
            renamed = workspace.get_entry(todo.id)
            assert renamed.title == "New name"

    asyncio.run(run())


def test_edit_works_from_highlighted_board_row(tmp_path) -> None:
    workspace = _make_workspace(tmp_path)
    app = DashboardTestApp(workspace)

    async def run():
        async with app.run_test() as pilot:
            panel = app.query_one(KnowledgePanel)
            await _wait_until(lambda: panel.table.row_count == 1, "seed", pilot)
            board_entry = workspace.find_entry_by_title("Board")
            panel._create_entry("note", "Second")
            await pilot.pause()

            # No explicit selection: Edit/Rename/Delete fall back to the row
            # under the table cursor (e.g. a row that was only highlighted).
            panel._selected_entry_id = None
            panel.table.cursor_coordinate = (0, 0)
            assert panel._current_entry().id == board_entry.id
            panel._save_entry_body(board_entry, "## Open\n\n- [ ] edited\n")
            await pilot.pause()
            assert workspace.get_entry(board_entry.id).body_md.endswith(
                "- [ ] edited\n"
            )
            assert panel._selected_entry_id == board_entry.id

    asyncio.run(run())


def test_delete_entry_removes_it(tmp_path) -> None:
    workspace = _make_workspace(tmp_path)
    app = DashboardTestApp(workspace)

    async def run():
        async with app.run_test() as pilot:
            panel = app.query_one(KnowledgePanel)
            await _wait_until(lambda: panel.table.row_count == 1, "seed", pilot)
            note = panel._create_entry("note", "Doomed")
            panel._delete_entry(note)
            await pilot.pause()
            assert workspace.get_entry(note.id) is None

    asyncio.run(run())
