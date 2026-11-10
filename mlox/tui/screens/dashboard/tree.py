"""Infrastructure tree widget."""

from __future__ import annotations

from hashlib import blake2b

from rich.text import Text
from textual.binding import Binding
from textual.widgets import Tree

from .model import (
    SelectionChanged,
    SelectionInfo,
    get_server_backends,
    get_service_capabilities,
    is_bundle_initialized,
)

CAPABILITY_LABELS = {
    "app": "App",
    "proxy": "Proxy",
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

# Only capabilities that describe a service's purpose belong in the tree.
# Operational contracts (health, logs, and bindings) remain available elsewhere.
SERVICE_PURPOSE_CAPABILITIES = frozenset({
    "app", "web_ui", "proxy", "secret_manager", "repository", "model_registry",
    "model_server", "monitor", "observability", "data_warehouse", "object_storage",
    "s3_object_storage", "spreadsheet", "database", "vector_database", "cache",
    "message_broker", "workflow_orchestrator", "feature_store", "container_registry",
    "deployment", "llm", "dashboard", "developer_tools",
})

# Muted colors stay consistent across services and dashboard refreshes. Plugin
# capabilities use a stable hash so their appearance does not depend on order.
CAPABILITY_COLORS = {
    "app": "#a58bb8",
    "proxy": "#b58979",
    "secret_manager": "#bd9a68",
    "secret_manager_binding": "#ad8e72",
    "health": "#8da276",
    "logs": "#899596",
    "repository": "#a18c80",
    "model_registry": "#b189a7",
    "model_server": "#8d8eb7",
    "monitor": "#83a39a",
    "observability": "#779b9b",
    "telemetry_binding": "#7995a9",
    "data_warehouse": "#b39b70",
    "object_storage": "#809fac",
    "s3_object_storage": "#7890ab",
    "spreadsheet": "#83a581",
    "database": "#8d9cbd",
    "vector_database": "#9d8fae",
    "cache": "#bba477",
    "message_broker": "#b58a84",
    "workflow_orchestrator": "#83a6a1",
    "feature_store": "#9da482",
    "container_registry": "#9c92a8",
    "deployment": "#9e9d78",
    "llm": "#af87a0",
    "dashboard": "#8d9ca0",
    "developer_tools": "#ac947d",
    "web_ui": "#a38ca8",
}


def capability_color(capability: str) -> str:
    if capability in CAPABILITY_COLORS:
        return CAPABILITY_COLORS[capability]
    colors = tuple(CAPABILITY_COLORS.values())
    index = int.from_bytes(blake2b(capability.encode(), digest_size=4).digest(), "big") % len(colors)
    return colors[index]


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

    # Keep row selection separate from expansion. The disclosure arrow remains
    # the only way to collapse or expand a branch.
    BINDINGS = [
        Binding("space", "ignore_tree_toggle", "", show=False),
        Binding("shift+space", "ignore_tree_toggle", "", show=False),
    ]

    def __init__(self) -> None:
        super().__init__("Infrastructure", id="infra-tree")
        self.auto_expand = False

    def action_ignore_tree_toggle(self) -> None:
        """Prevent keyboard selection from toggling branch expansion."""

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
            bundle_label = Text(str(bundle.name))
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


def service_tree_label(service: object) -> Text:
    """Return the compact service label used in the infrastructure tree."""

    label = Text(str(getattr(service, "name", "-")), style="#ffffff")
    capabilities = [capability for capability in get_service_capabilities(service)
                    if capability in SERVICE_PURPOSE_CAPABILITIES]
    if capabilities:
        label.append("  ")
        for index, capability in enumerate(capabilities):
            if index:
                label.append(" ")
            name = CAPABILITY_LABELS.get(capability, format_tree_token(capability)).lower()
            label.append(f" {name} ", style=f"#052628 on {capability_color(capability)}")
    return label


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
