"""Read-only file tree and content viewer widget."""

from __future__ import annotations

from typing import Any

from textual import on
from textual.app import ComposeResult
from textual.containers import Container, Horizontal
from textual.message import Message
from textual.widgets import TextArea, Tree


class FileBrowser(Container):
    """Reusable read-only file browser with a tree and content pane."""

    class FileSelected(Message):
        """A file was selected in the browser tree."""

        def __init__(
            self,
            file_browser: "FileBrowser",
            path: str,
            entry: dict[str, Any],
        ) -> None:
            self.file_browser = file_browser
            super().__init__()
            self.path = path
            self.entry = entry

        @property
        def control(self) -> "FileBrowser":
            """The file browser that emitted the selection."""

            return self.file_browser

    def __init__(self, *children, **kwargs) -> None:
        super().__init__(*children, **kwargs)
        self._entries: list[dict[str, Any]] = []
        self._title = "Files"

    def compose(self) -> ComposeResult:
        with Horizontal(id="file-browser-layout"):
            yield Tree("Files", id="file-browser-tree")
            yield TextArea("", id="file-browser-viewer")

    @property
    def tree(self) -> Tree:
        return self.query_one("#file-browser-tree", Tree)

    @property
    def viewer(self) -> TextArea:
        return self.query_one("#file-browser-viewer", TextArea)

    def on_mount(self) -> None:
        self.viewer.read_only = True
        self.show_message("Select a repository to load files.")

    def set_entries(self, entries: list[dict[str, Any]], *, title: str = "Files") -> None:
        """Replace the file tree with normalized entries."""

        self._entries = list(entries or [])
        self._title = title
        self._populate_tree()
        if self._entries:
            self.show_message("Select a file to view its content.")
        else:
            self.show_message("No files are available.")

    def show_loading(self, message: str = "Loading files...") -> None:
        self.tree.clear()
        self.tree.root.label = self._title
        self.tree.root.add_leaf(message)
        self.show_message(message)

    def show_message(self, message: str) -> None:
        self.viewer.load_text(str(message))

    def show_content(self, content: str, *, title: str = "File") -> None:
        self.viewer.border_title = title
        self.viewer.load_text(content)

    def _populate_tree(self) -> None:
        tree = self.tree
        tree.clear()
        tree.root.label = self._title
        nodes = {"": tree.root}
        if not self._entries:
            tree.root.add_leaf("No files")
            tree.root.expand_all()
            return

        for entry in sorted(
            self._entries,
            key=lambda item: (
                str(item.get("display_path", "")).count("/"),
                not item.get("is_dir", False),
                str(item.get("display_path", "")).lower(),
            ),
        ):
            display_path = str(entry.get("display_path", "")).strip("/")
            if not display_path:
                continue
            parts = display_path.split("/")
            parent_key = ""
            for part in parts[:-1]:
                node_key = f"{parent_key}/{part}".strip("/")
                if node_key not in nodes:
                    nodes[node_key] = nodes[parent_key].add(f"{part}/")
                parent_key = node_key

            label = parts[-1] + ("/" if entry.get("is_dir") else "")
            if entry.get("is_dir"):
                node_key = display_path
                nodes[node_key] = nodes.get(node_key) or nodes[parent_key].add(
                    label,
                    data=entry,
                )
            else:
                nodes[parent_key].add_leaf(label, data=entry)
        tree.root.expand_all()

    @on(Tree.NodeSelected, "#file-browser-tree")
    def handle_node_selected(self, event: Tree.NodeSelected) -> None:
        entry = event.node.data
        if not isinstance(entry, dict):
            return
        if not entry.get("is_file"):
            self.show_message("Select a file to view its content.")
            return
        path = str(entry.get("path") or "")
        if path:
            self.post_message(self.FileSelected(self, path, entry))
