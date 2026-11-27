"""Compile a policy into filter-chain rules, without applying them.

Installation, persistence, interaction with existing firewalls and rollback are
separate concerns. In particular, this module does not attach these chains.
"""

from __future__ import annotations

from dataclasses import dataclass
from ipaddress import ip_network
import re
import shlex
from typing import Literal

from mlox.firewall import FirewallPolicy


# Runs on the host while the firewall lock is held. Only our exact generated
# rules, backed by root-owned runtime metadata, can be excluded from the
# permanent-policy comparison or replayed after a chain replacement.
_TEMP_RULES_PROGRAM = r'''import pathlib, shlex, subprocess, sys, uuid
tool, table, chain, mode = sys.argv[1:]
args = [tool] + (["-t", table] if table else []) + ["-S", chain]
result = subprocess.run(args, capture_output=True, text=True)
if result.returncode and any(pathlib.Path("/run/mlox-firewall-grants").glob("*.grant")):
    print("Cannot inspect firewall chain while temporary grants exist", file=sys.stderr)
    sys.exit(1)
family = "4" if tool == "iptables" else "6"
target = "ACCEPT" if chain == "MLOX-POLICY-IN" else "RETURN"
base = 0
for line in result.stdout.splitlines():
    try: t = shlex.split(line)
    except ValueError:
        base += 1
        continue
    if not t or t[0] != "-A": continue
    valid = (len(t) == 13 and t[:5] == ["-A", chain, "-m", "set", "--match-set"]
             and t[6:10] == ["src", "-m", "comment", "--comment"]
             and t[11:] == ["-j", target] and t[10].startswith("mlox-temp-"))
    if valid:
        ident = t[10][10:]
        try: valid = len(ident) == 32 and uuid.UUID(ident).hex == ident
        except ValueError: valid = False
        if valid:
            name = "mlx" + family + ident[:24]
            try: valid = t[5] == name and pathlib.Path("/run/mlox-firewall-grants", name + ".owner").read_text() == ident and pathlib.Path("/run/mlox-firewall-grants", ident + ".grant").is_file()
            except OSError: valid = False
    if valid and mode == "restore":
        print(" ".join(["-I", chain, "1"] + t[2:]))
    if not valid: base += 1
if mode == "count": print(base)
'''


def _temporary_rules_command(tool: str, chain: str, mode: str, *, table: str = "") -> str:
    return shlex.join(("python3", "-c", _TEMP_RULES_PROGRAM, tool, table, chain, mode))


@dataclass(frozen=True)
class CompiledFirewallRules:
    """Rules for two *unattached* chains in one address family."""

    family: Literal[4, 6]
    input_rules: tuple[tuple[str, ...], ...]
    docker_rules: tuple[tuple[str, ...], ...]


@dataclass(frozen=True)
class FirewallIngressExtension:
    """Server-provided rules for pre-DNAT ingress and trusted host interfaces."""

    input_interfaces: tuple[str, ...]
    ipv4_rules: tuple[tuple[str, ...], ...]
    ipv6_rules: tuple[tuple[str, ...], ...]


def _extended_rules(rules: CompiledFirewallRules, extension: FirewallIngressExtension | None) -> CompiledFirewallRules:
    if extension is None:
        return rules
    extra = tuple(("-i", interface, "-j", "ACCEPT") for interface in extension.input_interfaces)
    return CompiledFirewallRules(rules.family, (*rules.input_rules[:-1], *extra, rules.input_rules[-1]), rules.docker_rules)


def _render_ingress_restore_payload(entries: tuple[tuple[str, ...], ...]) -> str:
    """Render restore syntax, which does not interpret shell single quotes."""
    lines = ["*mangle", ":MLOX-INGRESS - [0:0]", "-F MLOX-INGRESS"]
    for entry in entries:
        if any(re.fullmatch(r"[A-Za-z0-9_./,:+!\-]+", token) is None for token in entry):
            raise ValueError("Unsupported character in firewall restore rule.")
        lines.append(" ".join(("-A", "MLOX-INGRESS", *entry)))
    return "\n".join(lines) + "\n"


def _render_input_hook_check(tool: str, *, ingress: bool) -> str:
    first = f"$({tool} -S INPUT | grep '^-A INPUT ' | head -n 1)"
    expected = "-A INPUT -j MLOX-POLICY-IN"
    if not ingress:
        return f"test \"{first}\" = '{expected}'"
    # The K3s network-policy controller reconciles this jump to the head of
    # INPUT. The pre-DNAT ingress hook must independently remain first.
    second = f"$({tool} -S INPUT | grep '^-A INPUT ' | head -n 2 | tail -n 1)"
    kube_router = r'^-A INPUT -m comment --comment "kube-router netpol - [A-Z0-9]+" -j KUBE-ROUTER-INPUT$'
    return (f"first=\"{first}\"\n"
            f"if test \"$first\" != '{expected}'; then\n"
            f"  printf '%s\\n' \"$first\" | grep -Eq '{kube_router}'\n"
            f"  test \"{second}\" = '{expected}'\n"
            "fi")


def prepare_firewall_rules(policy: FirewallPolicy, ssh_port: int) -> tuple[CompiledFirewallRules, CompiledFirewallRules]:
    """Validate management access and compile both families before installation."""
    validate_ssh_policy(policy, ssh_port)
    return compile_firewall_rules(policy, 4), compile_firewall_rules(policy, 6)


def validate_ssh_policy(policy: FirewallPolicy, ssh_port: int) -> None:
    """Keep Ubuntu's configured management port accessible."""
    if type(ssh_port) is not int or not 1 <= ssh_port <= 65535:
        raise ValueError("The configured SSH port must be between 1 and 65535.")
    if ssh_port not in policy.public_tcp_ports:
        raise ValueError(f"The configured SSH port {ssh_port} must remain public.")


def render_unattached_chains(rules: CompiledFirewallRules) -> str:
    """Render a filter-table restore input for two new, unattached chains.

    The caller must use ``iptables-restore --noflush`` (or ip6tables-restore)
    and ensure neither chain is currently attached. This deliberately does not
    attach the chains or provide an installation operation.
    """
    input_chain = "MLOX-POLICY-IN"
    docker_chain = "MLOX-POLICY-DOCKER"
    lines = ["*filter", f":{input_chain} - [0:0]", f":{docker_chain} - [0:0]"]
    for chain, entries in ((input_chain, rules.input_rules), (docker_chain, rules.docker_rules)):
        lines.extend(shlex.join(("-A", chain, *entry)) for entry in entries)
    lines.append("COMMIT")
    return "\n".join(lines) + "\n"


def render_apply_script(policy: FirewallPolicy, ssh_port: int, *, docker: bool, ingress: FirewallIngressExtension | None = None) -> str:
    """Prepare and apply both filter tables. A failure may leave a partial change."""
    compiled = prepare_firewall_rules(policy, ssh_port)
    lines = [
        "set -eu", "umask 077", "exec 9>/run/lock/mlox-firewall.lock", "flock -x 9", "d=$(mktemp -d)",
        "trap 'rm -rf \"$d\"' EXIT HUP INT TERM",
    ]
    for rules in compiled:
        rules = _extended_rules(rules, ingress)
        tool = "iptables" if rules.family == 4 else "ip6tables"
        path = f'"$d/v{rules.family}"'
        payload = render_unattached_chains(rules)
        # Flush the managed chains inside the same restore transaction; --noflush
        # preserves all unrelated chains and rules.
        payload = payload.replace(":MLOX-POLICY-DOCKER - [0:0]\n", ":MLOX-POLICY-DOCKER - [0:0]\n-F MLOX-POLICY-IN\n-F MLOX-POLICY-DOCKER\n")
        payload = payload.removesuffix("COMMIT\n")
        lines.append(f"printf %s {shlex.quote(payload)} > {path}")
        lines.append(f"if {tool} -C INPUT -j MLOX-POLICY-IN 2>/dev/null; then printf '%s\\n' '-D INPUT -j MLOX-POLICY-IN' >> {path}; fi")
        lines.append(f"if {tool} -C INPUT -p tcp -j MLOX-FIREWALL 2>/dev/null; then printf '%s\\n' '-D INPUT -p tcp -j MLOX-FIREWALL' >> {path}; fi")
        lines.append(f"printf '%s\\n' '-I INPUT 1 -j MLOX-POLICY-IN' >> {path}")
        if docker:
            lines.append(f"{tool} -S DOCKER-USER >/dev/null")
        lines.append(f"if {tool} -S DOCKER-USER >/dev/null 2>&1; then")
        lines.append(f"  if {tool} -C DOCKER-USER -j MLOX-POLICY-DOCKER 2>/dev/null; then printf '%s\\n' '-D DOCKER-USER -j MLOX-POLICY-DOCKER' >> {path}; fi")
        lines.append(f"  if {tool} -C DOCKER-USER -p tcp -j MLOX-DOCKER-FIREWALL 2>/dev/null; then printf '%s\\n' '-D DOCKER-USER -p tcp -j MLOX-DOCKER-FIREWALL' >> {path}; fi")
        lines.append(f"  printf '%s\\n' '-I DOCKER-USER 1 -j MLOX-POLICY-DOCKER' >> {path}")
        lines.append("fi")
        for chain in ("MLOX-POLICY-IN", "MLOX-POLICY-DOCKER"):
            lines.append(f"{_temporary_rules_command(tool, chain, 'restore')} >> {path}")
        lines.append(f"printf '%s\\n' COMMIT >> {path}")
        if ingress is not None:
            entries = ingress.ipv4_rules if rules.family == 4 else ingress.ipv6_rules
            payload = _render_ingress_restore_payload(entries)
            lines.append(f"printf %s {shlex.quote(payload)} >> {path}")
            lines.append(f"{_temporary_rules_command(tool, 'MLOX-INGRESS', 'restore', table='mangle')} >> {path}")
            lines.append(f"if {tool} -t mangle -C PREROUTING -j MLOX-INGRESS 2>/dev/null; then printf '%s\\n' '-D PREROUTING -j MLOX-INGRESS' >> {path}; fi")
            lines.append(f"printf '%s\\n' '-I PREROUTING 1 -j MLOX-INGRESS' COMMIT >> {path}")
        lines.append(f"{tool}-restore --test --noflush < {path}")
    lines.extend([
        'iptables-restore --noflush < "$d/v4"',
        'ip6tables-restore --noflush < "$d/v6"',
        "printf '%s\\n' MLOX_POLICY_APPLIED",
    ])
    return "\n".join(lines)


def render_persist_script(policy: FirewallPolicy, ssh_port: int, *, docker: bool, ingress: FirewallIngressExtension | None = None) -> str:
    """Persist only a draft that exactly matches both live managed rule chains."""
    compiled = prepare_firewall_rules(policy, ssh_port)
    startup = "#!/bin/sh\n" + render_apply_script(policy, ssh_port, docker=docker, ingress=ingress) + "\n"
    ordering = "After=network-pre.target docker.service\nRequires=docker.service" if docker else "After=network-pre.target"
    unit = (
        "[Unit]\nDescription=Restore MLOX firewall policy\n"
        f"{ordering}\n"
        "[Service]\nType=oneshot\nExecStart=/bin/sh /etc/mlox/firewall/policy.sh\n"
        "RemainAfterExit=yes\n[Install]\nWantedBy=multi-user.target\n"
    )
    lines = ["set -eu", "umask 077", "exec 9>/run/lock/mlox-firewall.lock", "flock -x 9"]
    for rules in compiled:
        rules = _extended_rules(rules, ingress)
        tool = "iptables" if rules.family == 4 else "ip6tables"
        for chain, entries in (("MLOX-POLICY-IN", rules.input_rules), ("MLOX-POLICY-DOCKER", rules.docker_rules)):
            lines.append(f"test \"$({_temporary_rules_command(tool, chain, 'count')})\" -eq {len(entries)}")
            for entry in entries:
                lines.append(shlex.join((tool, "-C", chain, *entry)))
        lines.append(_render_input_hook_check(tool, ingress=ingress is not None))
        if docker:
            lines.append(f"test \"$({tool} -S DOCKER-USER | grep '^-A DOCKER-USER ' | head -n 1)\" = '-A DOCKER-USER -j MLOX-POLICY-DOCKER'")
        if ingress is not None:
            entries = ingress.ipv4_rules if rules.family == 4 else ingress.ipv6_rules
            lines.append(f"test \"$({_temporary_rules_command(tool, 'MLOX-INGRESS', 'count', table='mangle')})\" -eq {len(entries)}")
            for entry in entries:
                lines.append(shlex.join((tool, "-t", "mangle", "-C", "MLOX-INGRESS", *entry)))
            lines.append(f"test \"$({tool} -t mangle -S PREROUTING | grep '^-A PREROUTING ' | head -n 1)\" = '-A PREROUTING -j MLOX-INGRESS'")
    lines.extend([
        "install -d -m 0700 /etc/mlox/firewall",
        "p=$(mktemp /etc/mlox/firewall/.policy.XXXXXX)",
        "u=$(mktemp /etc/systemd/system/.mlox-firewall.XXXXXX)",
        "trap 'rm -f \"$p\" \"$u\"' EXIT HUP INT TERM",
        f"printf %s {shlex.quote(startup)} > \"$p\"",
        f"printf %s {shlex.quote(unit)} > \"$u\"",
        "chmod 0700 \"$p\"", "chmod 0644 \"$u\"",
        "mv -f \"$p\" /etc/mlox/firewall/policy.sh",
        "mv -f \"$u\" /etc/systemd/system/mlox-firewall-policy.service",
        "systemctl daemon-reload",
        "systemctl enable mlox-firewall-policy.service",
        "echo MLOX_POLICY_PERSISTED",
    ])
    return "\n".join(lines)


def compile_firewall_rules(policy: FirewallPolicy, family: Literal[4, 6]) -> CompiledFirewallRules:
    """Create ordered rule arguments for a host and Docker filter chain.

    Docker's allowed traffic returns to its caller rather than bypassing other
    Docker forwarding rules. The result must only be attached to INPUT and
    Docker's DOCKER-USER chain respectively, never arbitrary forwarding chains.
    ICMPv6 remains available for neighbour discovery and IPv6 error handling.
    """
    if family not in (4, 6):
        raise ValueError("Address family must be 4 or 6.")

    host: list[tuple[str, ...]] = [
        ("-i", "lo", "-j", "ACCEPT"),
        ("-m", "conntrack", "--ctstate", "ESTABLISHED,RELATED", "-j", "ACCEPT"),
        # Containers can reach host-published ports through Docker's gateway.
        # Restrict this to Docker's default bridge and standard named bridges;
        # a generic br+ would also trust unrelated host network bridges.
        ("-i", "docker0", "-j", "ACCEPT"),
        ("-i", "br-+", "-j", "ACCEPT"),
    ]
    docker: list[tuple[str, ...]] = [
        ("-m", "conntrack", "--ctstate", "ESTABLISHED,RELATED", "-j", "RETURN"),
        ("-i", "docker0", "-j", "RETURN"),
        ("-i", "br+", "-j", "RETURN"),
    ]
    if family == 6:
        host.append(("-p", "ipv6-icmp", "-j", "ACCEPT"))

    for source in policy.trusted_sources:
        if ip_network(source).version != family:
            continue
        host.append(("-s", source, "-j", "ACCEPT"))
        for bridge in ("docker0", "br+"):
            docker.append(("-o", bridge, "-s", source, "-j", "RETURN"))

    for port in policy.public_tcp_ports:
        host.append(("-p", "tcp", "--dport", str(port), "-j", "ACCEPT"))
        for bridge in ("docker0", "br+"):
            docker.append(("-o", bridge, "-p", "tcp", "-m", "conntrack", "--ctorigdstport", str(port), "-j", "RETURN"))

    host.append(("-j", "DROP"))
    for bridge in ("docker0", "br+"):
        docker.append(("-o", bridge, "-j", "DROP"))
    docker.append(("-j", "RETURN"))
    return CompiledFirewallRules(family, tuple(host), tuple(docker))
