"""Rich renderers for dashboard runtime information."""

from __future__ import annotations

from typing import Any

from rich.console import Group
from rich.table import Table
from rich.text import Text


def format_runtime_info(selection_type: str | None, data: dict[str, Any]) -> object:
    """Format runtime information for the selected dashboard node."""

    if selection_type == "bundle":
        backend_info = data.get("backend_info") or {}
        for formatter in (format_docker_backend, format_kubernetes_backend):
            rendered = formatter(backend_info)
            if rendered is not None:
                return rendered
        return "\n".join(format_mapping(backend_info))
    return format_server_info(data.get("server_info") or {})


def format_docker_backend(backend_info: object) -> object | None:
    """Render Docker backend status as a compact summary and containers table."""

    if not isinstance(backend_info, dict):
        return None
    if not any(str(key).startswith("docker.") for key in backend_info):
        return None

    containers = backend_info.get("docker.containers")
    container_count = str(len(containers)) if isinstance(containers, list) else "-"
    summary = " | ".join(
        [
            f"Docker: {format_bool(backend_info.get('docker.is_running'))}",
            f"Enabled: {format_bool(backend_info.get('docker.is_enabled'))}",
            f"Client: {docker_version(backend_info.get('docker.version'), 'Client')}",
            f"Server: {docker_version(backend_info.get('docker.version'), 'Server')}",
            f"Containers: {container_count}",
        ]
    )
    if not isinstance(containers, list):
        return runtime_group(summary, str(containers or "-"))

    container_table = Table(
        title="Containers",
        show_header=True,
        header_style="bold",
        expand=True,
    )
    container_table.add_column("Name", style="cyan", no_wrap=True)
    container_table.add_column("Image", no_wrap=True, overflow="ellipsis")
    container_table.add_column("State", no_wrap=True)
    container_table.add_column("Status", no_wrap=True, overflow="ellipsis")
    container_table.add_column("Ports", no_wrap=True, overflow="ellipsis")

    if containers:
        for container in containers:
            if not isinstance(container, dict):
                continue
            container_table.add_row(
                short_value(container.get("Names")),
                short_value(container.get("Image")),
                short_value(container.get("State")),
                short_value(container.get("Status")),
                short_value(container.get("Ports")),
            )
    else:
        container_table.add_row("-", "-", "-", "-", "-")

    return runtime_group(summary, container_table)


def format_kubernetes_backend(backend_info: object) -> object | None:
    """Render k3s backend status as a compact summary and nodes table."""

    if not isinstance(backend_info, dict):
        return None
    if not any(str(key).startswith("k3s") for key in backend_info):
        return None

    nodes = backend_info.get("k3s.nodes")
    node_count = str(len(nodes)) if isinstance(nodes, list) else "-"
    summary = " | ".join(
        [
            f"Backend: {format_bool(backend_info.get('backend.is_running'))}",
            f"k3s: {format_bool(backend_info.get('k3s.is_running'))}",
            f"agent: {format_bool(backend_info.get('k3s-agent.is_running'))}",
            f"nodes: {node_count}",
        ]
    )
    if not isinstance(nodes, list):
        return runtime_group(summary, "-")

    nodes_table = Table(
        title="Kubernetes Nodes",
        show_header=True,
        header_style="bold",
        expand=True,
    )
    nodes_table.add_column("Name", style="cyan", no_wrap=True)
    nodes_table.add_column("Status", no_wrap=True)
    nodes_table.add_column("Roles", no_wrap=True, overflow="ellipsis")
    nodes_table.add_column("Version", no_wrap=True)
    nodes_table.add_column("Internal IP", no_wrap=True)
    nodes_table.add_column("OS", overflow="ellipsis")
    nodes_table.add_column("Runtime", overflow="ellipsis")

    if nodes:
        for node in nodes:
            if not isinstance(node, dict):
                continue
            nodes_table.add_row(
                short_value(node.get("NAME")),
                short_value(node.get("STATUS")),
                short_value(node.get("ROLES")),
                short_value(node.get("VERSION")),
                short_value(node.get("INTERNAL-IP")),
                short_value(node.get("OS-IMAGE")),
                short_value(node.get("CONTAINER-RUNTIME")),
            )
    else:
        nodes_table.add_row("-", "-", "-", "-", "-", "-", "-")

    return runtime_group(summary, nodes_table)


def format_server_info(server_info: object) -> object:
    """Render server info as a compact system table."""

    if not isinstance(server_info, dict) or not server_info:
        return "-"

    table = Table(
        title="System",
        show_header=True,
        header_style="bold",
        expand=True,
    )
    table.add_column("Field", style="cyan", no_wrap=True)
    table.add_column("Value", overflow="fold")

    used_keys: set[str] = set()

    def add_row(key: str, label: str) -> None:
        value = server_info.get(key)
        if value in (None, ""):
            return
        used_keys.add(key)
        table.add_row(label, Text(str(value)))

    os_value = (
        server_info.get("pretty_name")
        or server_info.get("name")
        or server_info.get("id")
    )
    if os_value not in (None, ""):
        used_keys.update({"pretty_name", "name", "id"})

    add_row("host", "Host")
    if os_value not in (None, ""):
        table.add_row("OS", Text(str(os_value)))
    add_row("version_id", "Version")
    add_row("version_codename", "Codename")
    add_row("ubuntu_codename", "Ubuntu Codename")
    add_row("id_like", "ID Like")
    add_row("cpu_count", "CPU Cores")
    add_row("ram_gb", "RAM (GiB)")
    add_row("storage_gb", "Storage (GiB)")

    fallback_keys = [
        key
        for key in sorted(server_info, key=str)
        if key not in used_keys and not is_noisy_server_info_key(key)
    ]
    for key in fallback_keys[:8]:
        table.add_row(format_label(key), Text(str(server_info[key])))

    return table


def format_bool(value: object) -> str:
    if isinstance(value, bool):
        return "yes" if value else "no"
    return str(value) if value is not None else "-"


def runtime_group(summary: str, content: object) -> Group:
    """Combine compact runtime summary text with the detail renderable."""

    return Group(Text(summary), content)


def docker_version(version: object, section: str) -> str:
    if not isinstance(version, dict):
        return str(version) if version else "-"
    section_data = version.get(section)
    if isinstance(section_data, dict):
        return str(section_data.get("Version") or section_data.get("ApiVersion") or "-")
    return "-"


def short_value(value: object, *, limit: int = 80) -> str:
    text = str(value) if value not in (None, "") else "-"
    if len(text) <= limit:
        return text
    return text[: limit - 1] + "..."


def is_noisy_server_info_key(key: object) -> bool:
    text = str(key)
    return text.endswith("_url") or text in {"logo"}


def format_label(key: object) -> str:
    return str(key).replace("_", " ").title()


def format_mapping(values: object) -> list[str]:
    if not isinstance(values, dict) or not values:
        return ["-"]
    return [f"{key}: {values[key]!s}" for key in sorted(values, key=str)]
