"""Infrastructure tree widget."""

from __future__ import annotations

from rich.text import Text
from textual.widgets import Tree

from .model import (
    SelectionChanged,
    SelectionInfo,
    get_server_backends,
    get_service_capabilities,
    is_bundle_initialized,
)

SERVICE_CAPABILITY_PRIORITY = (
    "secret_manager",
    "monitor",
    "model_registry",
    "model_server",
    "repository",
    "database",
    "object_storage",
    "data_warehouse",
    "vector_database",
    "feature_store",
    "workflow_orchestrator",
    "message_broker",
    "container_registry",
    "deployment",
    "developer_tools",
    "llm",
    "dashboard",
    "web_ui",
)

CAPABILITY_LABELS = {
    "secret_manager": "Secret Manager",
    "model_registry": "Model Registry",
    "model_server": "Model Server",
    "object_storage": "Object Storage",
    "data_warehouse": "Data Warehouse",
    "vector_database": "Vector Database",
    "feature_store": "Feature Store",
    "workflow_orchestrator": "Workflow",
    "message_broker": "Message Broker",
    "container_registry": "Container Registry",
    "developer_tools": "Developer Tools",
    "web_ui": "Web UI",
    "llm": "LLM",
}

BACKEND_STYLES = {
    "connector": "bold bright_magenta",
    "docker": "bold bright_cyan",
    "k3s": "bold bright_green",
    "k3s_agent": "bold bright_green",
    "kubernetes": "bold bright_green",
    "local": "bold bright_blue",
    "multipass": "bold bright_yellow",
}


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
            bundle_label = Text(f"Bundle: {bundle.name}")
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
            bundle_node.add_leaf(
                server_tree_label(server),
                data=SelectionInfo(type="server", bundle=bundle, server=server),
            )
            for svc in bundle.services:
                bundle_node.add_leaf(
                    service_tree_label(svc),
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


def server_tree_label(server: object | None) -> Text:
    """Return the compact server label used in the infrastructure tree."""

    label = Text()
    backends = get_server_backends(server)
    if backends:
        for index, backend in enumerate(backends):
            if index:
                label.append(", ", style="dim")
            label.append(
                format_tree_token(backend),
                style=BACKEND_STYLES.get(backend, "bold bright_white"),
            )
    else:
        label.append("Unknown", style="bold yellow")
    label.append(": ", style="dim")
    label.append(str(getattr(server, "ip", "unknown")), style="dim")
    return label


def service_tree_label(service: object) -> str:
    """Return the compact service label used in the infrastructure tree."""

    name = str(getattr(service, "name", "-"))
    capability = primary_service_capability(service)
    return f"{capability}: {name}"


def primary_service_capability(service: object) -> str:
    """Return the most useful service capability label for tree scanning."""

    capabilities = set(get_service_capabilities(service))
    for capability in SERVICE_CAPABILITY_PRIORITY:
        if capability in capabilities:
            return CAPABILITY_LABELS.get(capability, format_tree_token(capability))
    return "Service"


def format_tree_token(value: str) -> str:
    """Format normalized backend/capability tokens for tree labels."""

    words = str(value).replace("-", "_").split("_")
    return " ".join(format_tree_word(word) for word in words if word)


def format_tree_word(word: str) -> str:
    acronyms = {
        "api": "API",
        "gcp": "GCP",
        "k3s": "K3s",
        "llm": "LLM",
        "ui": "UI",
    }
    return acronyms.get(word.lower(), word.capitalize())
