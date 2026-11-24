"""Ubuntu-specific helpers for temporary firewall access."""

from ipaddress import ip_address
from datetime import datetime, timezone
import json
import shlex
from uuid import UUID

from mlox.firewall_grants import FirewallAccessGrant, ssh_client_address


def observed_ssh_client(connection) -> str:
    """Use the SSH session that will manage this host, not a public IP service."""
    result = connection.run("printf '%s' \"$SSH_CONNECTION\"", hide=True, warn=False, pty=False, timeout=10)
    return ssh_client_address(result.stdout)


def grant_set_name(grant_id: str, family: int) -> str:
    """Use an ipset-compatible deterministic name for one grant and family."""
    if family not in (4, 6):
        raise ValueError("Address family must be 4 or 6.")
    try:
        value = UUID(grant_id).hex
    except (ValueError, TypeError, AttributeError) as exc:
        raise ValueError("Invalid grant identifier.") from exc
    # Linux ipset names are limited to 31 bytes. A collision is checked against
    # the full identifier in runtime metadata before any rule is changed.
    return f"mlx{family}{value[:24]}"


def compile_grant_rules(grant_id: str, address: str, *, docker: bool, k3s: bool) -> tuple[tuple[str, ...], ...]:
    """Build independent runtime rules; no rules or grant data are persisted."""
    source = ip_address(address)
    grant = UUID(grant_id).hex
    set_name = grant_set_name(grant, source.version)
    tool = "iptables" if source.version == 4 else "ip6tables"
    match = ("-m", "set", "--match-set", set_name, "src", "-m", "comment", "--comment", f"mlox-temp-{grant}")
    rules = [(tool, "-I", "MLOX-POLICY-IN", "1", *match, "-j", "ACCEPT")]
    if docker:
        rules.append((tool, "-I", "MLOX-POLICY-DOCKER", "1", *match, "-j", "RETURN"))
    if k3s:
        rules.append((tool, "-t", "mangle", "-I", "MLOX-INGRESS", "1", *match, "-j", "RETURN"))
    return tuple(rules)


def identify_grant_rule(rule: str, *, family: int, chain: str) -> str | None:
    """Recognize only the exact rule shape generated for a temporary grant.

    Comments alone are not sufficient: a modified rule bearing an MLOX comment
    must never be treated as an authorized temporary exception during policy
    verification or replay. ``rule`` is a single line from ``iptables -S``.
    """
    if family not in (4, 6):
        raise ValueError("Address family must be 4 or 6.")
    targets = {"MLOX-POLICY-IN": "ACCEPT", "MLOX-POLICY-DOCKER": "RETURN", "MLOX-INGRESS": "RETURN"}
    if chain not in targets:
        raise ValueError("Unknown temporary-access chain.")
    try:
        tokens = shlex.split(rule)
    except ValueError:
        return None
    if len(tokens) != 13 or tokens[:4] != ["-A", chain, "-m", "set"]:
        return None
    if tokens[4:5] != ["--match-set"] or tokens[6:10] != ["src", "-m", "comment", "--comment"]:
        return None
    if tokens[11:] != ["-j", targets[chain]] or not tokens[10].startswith("mlox-temp-"):
        return None
    grant_id = tokens[10].removeprefix("mlox-temp-")
    try:
        if len(grant_id) != 32 or UUID(grant_id).hex != grant_id:
            return None
        if tokens[5] != grant_set_name(grant_id, family):
            return None
    except (ValueError, TypeError):
        return None
    return grant_id


def render_grant_mutation(grant_id: str, *, address: str | None, duration_seconds: int | None,
                          docker: bool, k3s: bool) -> str:
    """Render an independently expiring grant or revoke it on an Ubuntu host.

    This deliberately does not install dependencies or alter the persistent
    firewall policy. Its caller must serialize it with policy operations and
    must obtain ``address`` from the SSH session managing the server.
    """
    grant = UUID(grant_id).hex
    if address is None:
        if duration_seconds is not None:
            raise ValueError("A removal cannot specify a duration.")
        source = None
    else:
        source = ip_address(address)
        if source.is_unspecified or source.is_loopback or source.is_multicast:
            raise ValueError("A grant requires a unicast client address.")
        if type(duration_seconds) is not int or not 1 <= duration_seconds <= 86400:
            raise ValueError("A grant duration must be between 1 and 86400 seconds.")
    if docker and k3s:
        raise ValueError("A server cannot use both Docker and K3s firewall paths.")

    lines = ["set -eu", "umask 077", "exec 9>/run/lock/mlox-firewall.lock", "flock -x 9",
             "command -v ipset >/dev/null", "install -d -m 0700 /run/mlox-firewall-grants"]
    # Check *both* names before touching either family. An ipset's 31-character
    # limit requires a truncated UUID; a collision must fail closed.
    for family in (4, 6):
        name = grant_set_name(grant, family)
        owner = f"/run/mlox-firewall-grants/{name}.owner"
        lines.extend([
            f"if test -e {owner}; then test \"$(cat {owner})\" = {grant} || exit 1;",
            f"elif ipset list {name} >/dev/null 2>&1; then exit 1; fi",
        ])
    if source is not None:
        lines.extend(["iptables -C INPUT -j MLOX-POLICY-IN", "ip6tables -C INPUT -j MLOX-POLICY-IN"])
        if docker:
            lines.extend(["iptables -C DOCKER-USER -j MLOX-POLICY-DOCKER", "ip6tables -C DOCKER-USER -j MLOX-POLICY-DOCKER"])
        if k3s:
            lines.extend(["iptables -t mangle -C PREROUTING -j MLOX-INGRESS", "ip6tables -t mangle -C PREROUTING -j MLOX-INGRESS"])
    # Empty the sets first, so a failed cleanup never leaves access behind.
    for family, sample in ((4, "192.0.2.1"), (6, "2001:db8::1")):
        name = grant_set_name(grant, family)
        owner = f"/run/mlox-firewall-grants/{name}.owner"
        lines.append(f"if test -e {owner}; then")
        lines.append(f"  if ipset list {name} >/dev/null 2>&1; then ipset flush {name}; fi")
        for rule in compile_grant_rules(grant, sample, docker=docker, k3s=k3s):
            index = rule.index("-I")
            check = (*rule[:index], "-C", rule[index + 1], *rule[index + 3:])
            delete = (*rule[:index], "-D", rule[index + 1], *rule[index + 3:])
            lines.append(f"  while {shlex.join(check)} 2>/dev/null; do {shlex.join(delete)}; done")
        lines.extend([f"  if ipset list {name} >/dev/null 2>&1; then ipset destroy {name}; fi", f"  rm -f {owner}", "fi"])
    record = f"/run/mlox-firewall-grants/{grant}.grant"
    lines.append(f"rm -f {record}")
    if source is not None:
        name = grant_set_name(grant, source.version)
        owner = f"/run/mlox-firewall-grants/{name}.owner"
        family = "inet" if source.version == 4 else "inet6"
        lines.extend([
            f"expiry=$(($(date +%s) + {duration_seconds}))",
            f"printf %s {grant} > {owner}",
            f"ipset create {name} hash:ip family {family} timeout {duration_seconds}",
            f"trap 'ipset flush {name} 2>/dev/null || true; rm -f {record}' EXIT",
            "trap 'exit 1' HUP INT TERM",
            f"ipset add {name} {source} timeout {duration_seconds}",
        ])
        lines.extend(shlex.join(rule) for rule in compile_grant_rules(grant, str(source), docker=docker, k3s=k3s))
        lines.extend([
            f"printf '%s %s %s\\n' {grant} {source} \"$expiry\" > {record}",
            "trap - EXIT HUP INT TERM",
            f"printf 'MLOX_GRANT %s %s %s\\n' {grant} {source} \"$expiry\"",
        ])
    else:
        lines.append("echo MLOX_GRANT_REMOVED")
    return "\n".join(lines)


_LIST_GRANTS_PROGRAM = r'''import ipaddress, json, pathlib, subprocess, time, uuid
root = pathlib.Path("/run/mlox-firewall-grants")
grants = []
for path in root.glob("*.grant"):
    try:
        ident, addr, expiry = path.read_text().split()
        addr = ipaddress.ip_address(addr)
        expiry = int(expiry)
        if len(ident) != 32 or uuid.UUID(ident).hex != ident or path.stem != ident: continue
        name = "mlx" + str(addr.version) + ident[:24]
        if (root / (name + ".owner")).read_text() != ident or expiry <= time.time(): continue
        result = subprocess.run(["ipset", "test", name, str(addr)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if result.returncode == 0: grants.append([ident, str(addr), expiry])
    except (FileNotFoundError, ValueError):
        if not path.exists(): continue
        raise
print("MLOX_GRANTS " + json.dumps(grants))
'''


def render_list_grants() -> str:
    return shlex.join(("python3", "-c", _LIST_GRANTS_PROGRAM))


def parse_grant_listing(output: str) -> tuple[FirewallAccessGrant, ...]:
    line = next((line for line in output.splitlines() if line.startswith("MLOX_GRANTS ")), None)
    if line is None:
        raise RuntimeError("Could not list temporary firewall grants.")
    try:
        rows = json.loads(line.removeprefix("MLOX_GRANTS "))
        if not isinstance(rows, list):
            raise ValueError("Invalid grant listing.")
        return tuple(FirewallAccessGrant(ident, address, datetime.fromtimestamp(expiry, timezone.utc))
                     for ident, address, expiry in rows)
    except (ValueError, TypeError, OverflowError, OSError) as exc:
        raise RuntimeError("Invalid temporary firewall grant listing.") from exc
