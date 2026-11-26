"""Low-impact connectivity checks for a single selected project server."""

from __future__ import annotations

import socket
import time

from mlox.application.result import OperationResult


# Deliberately small and fixed: one TCP connection attempt per common port.
SAFE_TCP_PORTS = (22, 80, 443, 3000, 5000, 5432, 8080, 8443, 9000)


def check_common_tcp_ports(server, *, timeout: float = 0.4) -> OperationResult:
    """Probe a short list of common ports on exactly one selected server."""

    host = str(getattr(server, "ip", "") or "").strip()
    if not host:
        return OperationResult(False, 1, "The selected server has no address to check.")

    rows: list[dict[str, object]] = []
    for port in SAFE_TCP_PORTS:
        started = time.monotonic()
        try:
            with socket.create_connection((host, port), timeout=timeout):
                state = "open"
        except (OSError, TimeoutError):
            state = "closed or filtered"
        rows.append({"port": port, "state": state, "milliseconds": round((time.monotonic() - started) * 1000)})
        time.sleep(0.05)
    return OperationResult(
        True,
        0,
        f"Checked {len(rows)} common TCP ports on {host}. This is a reachability check, not a vulnerability scan.",
        {"host": host, "ports": rows},
    )
