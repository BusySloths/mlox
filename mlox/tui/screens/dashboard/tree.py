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

# Vivid colors stay consistent across services and dashboard refreshes. Plugin
# capabilities use a stable hash so their appearance does not depend on order.
CAPABILITY_COLORS = {
    "app": "#e879f9",
    "proxy": "#fb923c",
    "secret_manager": "#fbbf24",
    "secret_manager_binding": "#f9a8d4",
    "health": "#a3e635",
    "logs": "#67e8f9",
    "repository": "#fdba74",
    "model_registry": "#f472b6",
    "model_server": "#a78bfa",
    "monitor": "#5eead4",
    "observability": "#2dd4bf",
    "telemetry_binding": "#7dd3fc",
    "data_warehouse": "#facc15",
    "object_storage": "#38bdf8",
    "s3_object_storage": "#60a5fa",
    "spreadsheet": "#86efac",
    "database": "#93c5fd",
    "vector_database": "#c084fc",
    "cache": "#fde047",
    "message_broker": "#fb7185",
    "workflow_orchestrator": "#5eead4",
    "feature_store": "#bef264",
    "container_registry": "#c4b5fd",
    "deployment": "#d9f99d",
    "llm": "#f0abfc",
    "dashboard": "#67e8f9",
    "developer_tools": "#fdba74",
    "web_ui": "#f5a3ed",
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



def service_capability_badges(service: object) -> Text:
    """Show every capability with stable colors in the selection summary."""
    badges = Text()
    for capability in get_service_capabilities(service):
        if badges:
            badges.append(" ")
        badges.append(
            f" {format_tree_token(capability)} ",
            style=f"bold #25102d on {capability_color(capability)}",
        )
    return badges


# Specific roles precede broad capabilities such as database, app, and web UI.
PRIMARY_ROLE_PRIORITY = (
    "secret_manager", "proxy", "workflow_orchestrator", "feature_store",
    "model_registry", "model_server", "llm", "vector_database", "cache",
    "object_storage", "s3_object_storage", "data_warehouse", "message_broker",
    "container_registry", "repository", "observability", "monitor",
    "spreadsheet", "database", "deployment", "developer_tools", "dashboard",
    "app", "web_ui",
)
CAPABILITY_LABELS.update({
    "secret_manager": "Secrets", "message_broker": "Messaging",
    "observability": "Observability", "monitor": "Monitoring",
    "s3_object_storage": "Object Storage",
})


def primary_service_role(service: object) -> str:
    """Choose a stable, specific purpose independent of capability ordering."""
    capabilities = set(get_service_capabilities(service))
    for capability in PRIMARY_ROLE_PRIORITY:
        if capability in capabilities:
            return CAPABILITY_LABELS.get(capability, format_tree_token(capability))
    return ""


class InfraTree(Tree[SelectionInfo]):
    """Tree showing the current infrastructure bundles, servers and services."""

    DEFAULT_CSS = "InfraTree { width: 1fr; height: 1fr; overflow-x: hidden; }"

    # Keep row selection separate from expansion. The disclosure arrow remains
    # the only way to collapse or expand a branch.
    BINDINGS = [
        Binding("space", "ignore_tree_toggle", "", show=False),
        Binding("shift+space", "ignore_tree_toggle", "", show=False),
    ]

    def __init__(self) -> None:
        super().__init__("Infrastructure", id="infra-tree")
        self.auto_expand = False
        self.show_guides = True
        self.guide_depth = 2

    def action_ignore_tree_toggle(self) -> None:
        """Prevent keyboard selection from toggling branch expansion."""

    def on_mount(self) -> None:
        self.populate_tree()

    def populate_tree(self) -> None:
        """Populate the tree with bundles, servers and services."""

        self.clear()
        workspace = getattr(self.app, "workspace", None)
        project_name = getattr(workspace, "name", None)
        self.root.label = Text(project_name or "Infrastructure", style="bold")
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
            backends = get_server_backends(server)
            bundle_style = (
                BACKEND_STYLES.get(backends[0], "bold bright_white")
                if backends else "bold yellow"
            )
            bundle_label = Text(str(bundle.name).upper(), style=bundle_style)
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
    label.append(" · ", style="dim")
    label.append(str(getattr(server, "ip", "unknown")), style="dim")
    return label


def service_tree_label(service: object) -> Text:
    """Keep the main capability before the name at every sidebar width."""
    label = Text()
    role = primary_service_role(service)
    if role:
        label.append(role, style="dim")
        label.append(" · ", style="dim")
    label.append(str(getattr(service, "name", "-")))
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
