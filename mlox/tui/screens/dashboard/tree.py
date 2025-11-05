"""Infrastructure tree widget."""

from __future__ import annotations

from typing import Optional

from textual.widgets import Tree

from mlox.session import MloxSession

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
        session: Optional[MloxSession] = getattr(self.app, "session", None)
        project_name = getattr(getattr(session, "project", None), "name", None)
        self.root.label = project_name or "Infrastructure"
        self.root.data = SelectionInfo(
            type="root", bundle=None, server=None, service=None
        )

        infra = getattr(session, "infra", None)
        if not infra or not infra.bundles:
            self.root.add(
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
            bundle_node.add(
                server_label,
                data=SelectionInfo(type="server", bundle=bundle, server=server),
            )
            if not bundle.services:
                bundle_node.add("No services", data=SelectionInfo(type="empty"))
                continue
            for svc in bundle.services:
                bundle_node.add(
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
