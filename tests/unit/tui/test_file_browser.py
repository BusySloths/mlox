from __future__ import annotations

import asyncio

from textual.app import App, ComposeResult

from mlox.tui.widgets.file_browser import FileBrowser


class FileBrowserTestApp(App):
    def __init__(self) -> None:
        super().__init__()
        self.selected_paths: list[str] = []

    def compose(self) -> ComposeResult:
        yield FileBrowser()

    def on_file_browser_file_selected(self, message: FileBrowser.FileSelected) -> None:
        self.selected_paths.append(message.path)


async def _render_nested_tree_and_select_file() -> tuple[list[str], str]:
    app = FileBrowserTestApp()
    async with app.run_test() as pilot:
        browser = app.query_one(FileBrowser)
        browser.set_entries(
            [
                {
                    "name": "src",
                    "path": "/repo/src",
                    "display_path": "src",
                    "is_dir": True,
                },
                {
                    "name": "app.py",
                    "path": "/repo/src/app.py",
                    "display_path": "src/app.py",
                    "is_file": True,
                    "size": 12,
                },
            ],
            title="demo",
        )
        await pilot.pause()
        file_node = browser.tree.root.children[0].children[0]
        browser.tree.move_cursor(file_node)
        browser.tree.action_select_cursor()
        await pilot.pause()
        labels = [
            browser.tree.root.label.plain,
            browser.tree.root.children[0].label.plain,
            file_node.label.plain,
        ]
        return labels, app.selected_paths[0]


def test_file_browser_renders_nested_tree_and_emits_selected_file() -> None:
    labels, selected_path = asyncio.run(_render_nested_tree_and_select_file())

    assert labels == ["demo", "src/", "app.py"]
    assert selected_path == "/repo/src/app.py"


async def _empty_file_browser_message() -> str:
    app = FileBrowserTestApp()
    async with app.run_test() as pilot:
        browser = app.query_one(FileBrowser)
        browser.set_entries([])
        await pilot.pause()
        return browser.viewer.text


def test_file_browser_handles_empty_entries() -> None:
    assert asyncio.run(_empty_file_browser_message()) == "No files are available."
