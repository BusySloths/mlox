"""Ubuntu firewall observations translated into the server contract."""

from __future__ import annotations

from mlox.executors import UbuntuTaskExecutor
from mlox.firewall import FirewallStatus


def parse_firewall_status(raw: str | None) -> FirewallStatus:
    if raw is None:
        return FirewallStatus(active=None, error="Firewall status could not be retrieved.")
    if "Status: active" in raw:
        active = True
    elif "Status: inactive" in raw:
        active = False
    else:
        return FirewallStatus(active=None, error="Unrecognized firewall status.", raw=raw)
    error = ("Policy is active in only one IP address family."
             if "Warning: policy missing in one address family" in raw else "")
    rules = UbuntuTaskExecutor._parse_iptables_allowed_rules(raw) or set()
    trusted = set()
    for line in raw.splitlines():
        tokens = line.split()
        if (tokens[:2] == ["-A", "MLOX-POLICY-IN"] and "-s" in tokens
                and "--dport" not in tokens and tokens[-2:] == ["-j", "ACCEPT"]):
            trusted.add(UbuntuTaskExecutor._normalize_firewall_source(tokens[tokens.index("-s") + 1]))
    persistence = next((line.removeprefix("Persistence: ") for line in raw.splitlines()
                        if line.startswith("Persistence: ")), "unknown")
    if persistence not in ("enabled", "disabled"):
        persistence = "unknown"
    return FirewallStatus(
        active=active, persistence=persistence,
        allowed_ports=tuple(sorted({port for port, _ in rules})),
        public_ports=tuple(sorted({port for port, source in rules if source is None})),
        trusted_sources=tuple(sorted(trusted)), error=error,
        previous_policy="-N MLOX-FIREWALL" in raw and "-N MLOX-POLICY-IN" not in raw,
        raw=raw,
    )
