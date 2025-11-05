"""Shared dashboard data structures and helpers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional

from textual.message import Message

from mlox.session import MloxSession

WELCOME_TEXT = """\
Accelerate your ML journey—deploy production-ready MLOps in minutes, not months.

MLOX helps individuals and small teams deploy, configure, and monitor full
MLOps stacks with minimal effort.
"""


@dataclass
class SelectionInfo:
    """Normalized information about the selected tree node."""

    type: str
    bundle: Any | None = None
    server: Any | None = None
    service: Any | None = None


class SelectionChanged(Message):
    """Message broadcast whenever the tree selection changes."""

    def __init__(self, selection: Optional[SelectionInfo]) -> None:
        super().__init__()
        self.selection = selection


def summarize_infrastructure(session: Optional[MloxSession]) -> Dict[str, Any]:
    """Return aggregate statistics and listings for the active session."""

    summary: Dict[str, Any] = {
        "has_data": False,
        "totals": {"bundles": 0, "servers": 0, "services": 0, "cpu": 0.0, "ram": 0.0},
        "cpu_available": False,
        "ram_available": False,
        "server_rows": [],
        "service_rows": [],
    }
    if not session:
        return summary
    infra = getattr(session, "infra", None)
    if not infra or not getattr(infra, "bundles", None):
        return summary

    summary["has_data"] = True
    bundles = infra.bundles
    summary["totals"]["bundles"] = len(bundles)
    for bundle in bundles:
        services = getattr(bundle, "services", []) or []
        server = getattr(bundle, "server", None)
        if server:
            summary["totals"]["servers"] += 1
            service_count = len(services)
            summary["server_rows"].append(
                (
                    getattr(server, "ip", "unknown"),
                    getattr(server, "state", "unknown"),
                    service_count,
                )
            )
            try:
                info = server.get_server_info()
            except Exception:  # pragma: no cover - defensive against IO errors
                info = {}
            cpu_count = info.get("cpu_count") if isinstance(info, dict) else None
            ram_gb = info.get("ram_gb") if isinstance(info, dict) else None
            if isinstance(cpu_count, (int, float)):
                summary["cpu_available"] = True
                summary["totals"]["cpu"] += float(cpu_count)
            if isinstance(ram_gb, (int, float)):
                summary["ram_available"] = True
                summary["totals"]["ram"] += float(ram_gb)
        for svc in services:
            summary["totals"]["services"] += 1
            summary["service_rows"].append(
                (
                    getattr(svc, "name", "-"),
                    getattr(svc, "service_config_id", "-"),
                    getattr(server, "ip", "unknown") if server else "-",
                    getattr(svc, "state", "unknown"),
                )
            )
    return summary
