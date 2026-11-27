from __future__ import annotations

from typing import Any
from dataclasses import asdict

from mlox.application.result import OperationResult
from mlox.server import ServerCapability
from mlox.firewall import FirewallPolicy, FirewallStatus


def preview_firewall_policy(infra, bundle) -> OperationResult:
    """Describe a default policy and unverified project-server candidates.

    An address in the project does not prove outbound source address, reachability,
    or stability. Candidates therefore do not become trusted sources automatically.
    """
    server = getattr(bundle, "server", None)
    if not _has_firewall_capability(server):
        return OperationResult(False, 1, "Server does not support firewall management.")
    try:
        policy = _draft_policy(bundle)
        fixed_rules = [asdict(rule) for rule in server.firewall_policy_rules()]
    except (ValueError, TypeError, KeyError) as exc:
        return OperationResult(False, 2, f"Invalid firewall draft or server SSH port: {exc}")
    candidates = []
    for other in getattr(infra, "bundles", []) or []:
        peer = getattr(other, "server", None)
        if peer is None or other is bundle or peer is server:
            continue
        get_address = getattr(peer, "firewall_peer_address", None)
        address = get_address() if callable(get_address) else None
        if not address:
            continue
        candidates.append({
            "bundle": str(getattr(other, "name", "-")),
            "address": str(address),
            "verified": False,
        })
    return OperationResult(True, 0, "Firewall policy preview; no rules changed.", {
        "bundle": str(getattr(bundle, "name", "-")),
        "public_tcp_ports": list(policy.public_tcp_ports),
        "trusted_sources": list(policy.trusted_sources),
        "fixed_rules": fixed_rules,
        "draft_saved": getattr(bundle, "firewall_policy_draft", None) is not None,
        "suggested_project_sources": candidates,
        "warning": "Suggested addresses are unverified; check their outbound source address, stability and reachability before trusting them.",
    })


def _draft_policy(bundle) -> FirewallPolicy:
    draft = getattr(bundle, "firewall_policy_draft", None)
    if draft is None:
        policy = bundle.server.firewall_default_policy()
    else:
        policy = FirewallPolicy(tuple(draft["public_tcp_ports"]), tuple(draft["trusted_sources"]))
    bundle.server.firewall_validate_policy(policy)
    return policy


def update_firewall_draft_source(bundle, source: str, *, remove: bool = False) -> OperationResult:
    """Change a local policy draft; never modify the live firewall."""
    if not _has_firewall_capability(getattr(bundle, "server", None)):
        return OperationResult(False, 1, "Server does not support firewall management.")
    try:
        policy = _draft_policy(bundle)
        policy = policy.without_source(source) if remove else policy.with_source(source)
    except (ValueError, TypeError, KeyError) as exc:
        return OperationResult(False, 2, f"Invalid firewall policy or source: {exc}")
    bundle.firewall_policy_draft = {
        "public_tcp_ports": list(policy.public_tcp_ports),
        "trusted_sources": list(policy.trusted_sources),
    }
    return OperationResult(True, 0, "Firewall draft saved; live firewall unchanged.", {
        "bundle": str(getattr(bundle, "name", "-")),
        "public_tcp_ports": list(policy.public_tcp_ports),
        "trusted_sources": list(policy.trusted_sources),
        "applied": False,
    })


def replace_firewall_draft_sources(bundle, sources: list[str]) -> OperationResult:
    """Replace trusted sources in one draft update without changing live rules."""
    if not _has_firewall_capability(getattr(bundle, "server", None)):
        return OperationResult(False, 1, "Server does not support firewall management.")
    try:
        current = _draft_policy(bundle)
        policy = FirewallPolicy(current.public_tcp_ports, tuple(sources))
    except (ValueError, TypeError, KeyError) as exc:
        return OperationResult(False, 2, f"Invalid firewall policy or source: {exc}")
    bundle.firewall_policy_draft = {
        "public_tcp_ports": list(policy.public_tcp_ports),
        "trusted_sources": list(policy.trusted_sources),
    }
    return OperationResult(True, 0, "Firewall draft saved; live firewall unchanged.", {
        "bundle": str(getattr(bundle, "name", "-")),
        "public_tcp_ports": list(policy.public_tcp_ports),
        "trusted_sources": list(policy.trusted_sources),
        "applied": False,
    })


def apply_firewall_draft(bundle) -> OperationResult:
    """Apply the selected server's draft; failures may leave partial rules."""
    server = getattr(bundle, "server", None)
    if not _has_firewall_capability(server):
        return OperationResult(False, 1, "Server does not support firewall management.")
    try:
        policy = _draft_policy(bundle)
        server.firewall_apply_policy(policy)
    except Exception as exc:
        return OperationResult(False, 2, f"Could not apply firewall policy: {exc}")
    result = describe_bundle_firewall(bundle)
    result.message = "Firewall policy applied temporarily. A previously persisted policy may return after reboot."
    result.data["applied"] = True
    result.data["persistence"] = "Runtime rules; reapply after a server reboot."
    return result


def persist_firewall_draft(bundle) -> OperationResult:
    """Persist the draft only if it matches the server's applied policy."""
    server = getattr(bundle, "server", None)
    if not _has_firewall_capability(server):
        return OperationResult(False, 1, "Server does not support firewall management.")
    try:
        server.firewall_persist_policy(_draft_policy(bundle))
    except Exception as exc:
        return OperationResult(False, 2, f"Could not make firewall policy permanent: {exc}")
    result = describe_bundle_firewall(bundle)
    result.message = "Applied firewall policy configured to return after reboot."
    result.data["persisted"] = True
    return result


def describe_project_firewalls(infra) -> OperationResult:
    """Return firewall status for every firewall-capable bundle."""

    bundles = _firewall_bundles(infra)
    rows = []
    active_count = 0
    unknown_count = 0
    for bundle in bundles:
        detail = _describe_bundle(bundle)
        rows.append(detail)
        if detail["status_error"]:
            unknown_count += 1
        elif detail["is_active"]:
            active_count += 1

    return OperationResult(
        True,
        0,
        "Firewall status loaded.",
        {
            "rows": rows,
            "summary": {
                "capable": len(rows),
                "active": active_count,
                "inactive": len(rows) - active_count - unknown_count,
                "unknown": unknown_count,
            },
        },
    )


def describe_bundle_firewall(bundle) -> OperationResult:
    return OperationResult(
        True,
        0,
        f"Firewall status loaded for {getattr(bundle, 'name', '-')}.",
        {"firewall": _describe_bundle(bundle)},
    )


def disable_bundle_firewall(bundle) -> OperationResult:
    try:
        bundle.server.firewall_down()
    except Exception as exc:
        return OperationResult(
            False,
            2,
            f"Could not disable firewall for {getattr(bundle, 'name', '-')}: {exc}",
        )
    return describe_bundle_firewall(bundle)


def firewall_summary_for_bundle(bundle) -> dict[str, Any]:
    server = getattr(bundle, "server", None)
    return {"capable": _has_firewall_capability(server)}


def _firewall_bundles(infra) -> list:
    return [
        bundle
        for bundle in getattr(infra, "bundles", []) or []
        if _has_firewall_capability(getattr(bundle, "server", None))
    ]


def _describe_bundle(bundle) -> dict[str, Any]:
    server = getattr(bundle, "server", None)
    try:
        status = server.firewall_status()
        if not isinstance(status, FirewallStatus):
            raise TypeError("Server returned an invalid firewall status.")
    except Exception as exc:
        status = FirewallStatus(active=None, error=str(exc))

    is_active = status.active is True
    error = status.error or ("Firewall status could not be retrieved." if status.active is None else "")

    return {
        "id": str(getattr(server, "uuid", getattr(bundle, "name", ""))),
        "bundle": getattr(bundle, "name", "-"),
        "server": str(getattr(server, "ip", "-")),
        "server_state": str(getattr(server, "state", "unknown")),
        "is_active": is_active,
        "status": "Unknown" if error else "Active" if is_active else "Inactive",
        "status_error": error,
        "persistence": status.persistence,
        "open_ports": list(status.allowed_ports),
        "public_ports": list(status.public_ports),
        "trusted_sources": list(status.trusted_sources),
        "temporary_grants": (None if status.temporary_grants is None else [
            {"grant_id": grant.grant_id, "address": grant.address, "expires_at": grant.expires_at.isoformat()}
            for grant in status.temporary_grants
        ]),
        "legacy_policy": status.previous_policy,
        "open_ports_unknown": status.active is None,
        "raw_status": status.raw,
        "bundle_ref": bundle,
    }


def _has_firewall_capability(server) -> bool:
    capabilities = getattr(server, "capabilities", set()) or set()
    return ServerCapability.FIREWALL in capabilities or "firewall" in capabilities
