"""Infrastructure tree widget."""

from __future__ import annotations

from rich.text import Text
from textual.widgets import Tree

from .model import (
    SelectionChanged,
    SelectionInfo,
    get_server_backends,
    is_bundle_initialized,
)


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
            self.expand_all()
            return

        for bundle in infra.bundles:
            server = getattr(bundle, "server", None)
            backends = ", ".join(get_server_backends(server)) or "unknown"
            bundle_label = Text(f"Bundle: {bundle.name}")
            bundle_label.append("  Backend: ", style="dim")
            bundle_label.append(backends, style="bold cyan")
            if not is_bundle_initialized(bundle):
                bundle_label.append("  State: ", style="dim")
                bundle_label.append("pending", style="bold yellow")
                self.root.add_leaf(
                    bundle_label,
                    data=SelectionInfo(type="bundle", bundle=bundle, server=server),
                )
                continue
            bundle_node = self.root.add(
                bundle_label,
                data=SelectionInfo(type="bundle", bundle=bundle, server=server),
            )
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
        self.expand_all()

    def expand_all(self) -> None:
        """Expand every non-leaf node currently present in the tree."""

        self.root.expand_all()

    def on_tree_node_selected(
        self, event: Tree.NodeSelected
    ) -> None:  # pragma: no cover - UI callback
        data = event.node.data
        selection = data if isinstance(data, SelectionInfo) else None
        self.post_message(SelectionChanged(selection))
