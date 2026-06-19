"""Infrastructure tree widget."""

from __future__ import annotations

from rich.text import Text
from textual.widgets import Tree

from .model import SelectionChanged, SelectionInfo


class InfraTree(Tree[SelectionInfo]):
    """Tree showing the current infrastructure bundles, servers and services."""

    def __init__(self) -> None:
        super().__init__("Infrastructure", id="infra-tree")

    def on_mount(self) -> None:
        self.populate_tree()

    def populate_tree(self) -> None:
        """Populate the tree with bundles, servers and services."""

        self.clear()
        workspace = getattr(self.app, "workspace", None)
        project_name = getattr(workspace, "name", None)
        active_secret_manager = getattr(
            workspace, "active_secret_manager_name", "Unknown"
        )
        root_label = Text(project_name or "Infrastructure")
        root_label.append("  Secrets: ", style="dim")
        root_label.append(active_secret_manager, style="bold green")
        self.root.label = root_label
        self.root.data = SelectionInfo(
            type="root", bundle=None, server=None, service=None
        )

        infra = getattr(workspace, "infrastructure", None)
        if not infra or not infra.bundles:
            self.root.add_leaf(
                "No infrastructure available", data=SelectionInfo(type="empty")
            )
            self.root.expand()
            return

        for bundle in infra.bundles:
            bundle_node = self.root.add(
                f"Bundle: {bundle.name}",
                data=SelectionInfo(type="bundle", bundle=bundle, server=bundle.server),
            )
            bundle_node.expand()
            server = getattr(bundle, "server", None)
            server_label = (
                f"Server: {getattr(server, 'ip', 'unknown')}"
                if server
                else "Server: unknown"
            )
            bundle_node.add_leaf(
                server_label,
                data=SelectionInfo(type="server", bundle=bundle, server=server),
            )
            if not bundle.services:
                bundle_node.add_leaf("No services", data=SelectionInfo(type="empty"))
                continue
            for svc in bundle.services:
                bundle_node.add_leaf(
                    f"Service: {svc.name}",
                    data=SelectionInfo(
                        type="service", bundle=bundle, server=server, service=svc
                    ),
                )
        self.root.expand()

    def on_tree_node_selected(
        self, event: Tree.NodeSelected
    ) -> None:  # pragma: no cover - UI callback
        data = event.node.data
        selection = data if isinstance(data, SelectionInfo) else None
        self.post_message(SelectionChanged(selection))
