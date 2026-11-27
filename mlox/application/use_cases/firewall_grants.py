"""Project-level orchestration for temporary client firewall grants."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from uuid import UUID

from mlox.application.result import OperationResult
from mlox.firewall_grants import FirewallAccessGrant
from mlox.server import ServerCapability


def grant_current_computer(infra, *, grant_id: str, duration_seconds: int) -> OperationResult:
    """Request the current SSH source on every firewall-capable project server."""
    try:
        normalized_id = UUID(grant_id).hex
    except (ValueError, AttributeError, TypeError):
        return OperationResult(False, 1, "Invalid temporary access grant identifier.")
    if type(duration_seconds) is not int or not 1 <= duration_seconds <= 86400:
        return OperationResult(False, 2, "Temporary access duration must be between 1 second and 24 hours.")

    bundles = [bundle for bundle in getattr(infra, "bundles", ())
               if ServerCapability.FIREWALL in getattr(bundle.server, "capabilities", set())]
    if not bundles:
        return OperationResult(False, 3, "No firewall-capable servers found.", {"servers": []})

    def apply(bundle):
        result = {"server": str(getattr(bundle, "name", ""))}
        try:
            grant = bundle.server.firewall_grant_current_client(normalized_id, duration_seconds)
            if grant is None:
                result.update(status="skipped", message="Firewall is inactive.")
            elif not isinstance(grant, FirewallAccessGrant) or grant.grant_id != normalized_id:
                result.update(status="failed", message="Server returned an invalid grant.")
            else:
                result.update(status="added", address=grant.address, expires_at=grant.expires_at.isoformat())
        except Exception as exc:
            result.update(status="failed", message=str(exc))
        return result

    with ThreadPoolExecutor(max_workers=min(4, len(bundles))) as executor:
        results = list(executor.map(apply, bundles))
    failed = sum(row["status"] == "failed" for row in results)
    added = sum(row["status"] == "added" for row in results)
    skipped = len(results) - failed - added
    success = failed == 0 and added > 0
    return OperationResult(success, 0 if success else 4,
                           f"Temporary access: {added} added, {skipped} skipped, {failed} failed.",
                           {"grant_id": normalized_id, "servers": results})


def remove_computer_grant(infra, *, grant_id: str) -> OperationResult:
    """Revoke one computer's grant on all capable project servers."""
    try:
        normalized_id = UUID(grant_id).hex
    except (ValueError, AttributeError, TypeError):
        return OperationResult(False, 1, "Invalid temporary access grant identifier.")
    bundles = [bundle for bundle in getattr(infra, "bundles", ())
               if ServerCapability.FIREWALL in getattr(bundle.server, "capabilities", set())]
    if not bundles:
        return OperationResult(False, 3, "No firewall-capable servers found.", {"servers": []})

    def remove(bundle):
        result = {"server": str(getattr(bundle, "name", ""))}
        try:
            bundle.server.firewall_remove_client_grant(normalized_id)
            result.update(status="removed")
        except Exception as exc:
            result.update(status="failed", message=str(exc))
        return result

    with ThreadPoolExecutor(max_workers=min(4, len(bundles))) as executor:
        results = list(executor.map(remove, bundles))
    failed = sum(row["status"] == "failed" for row in results)
    return OperationResult(failed == 0, 0 if not failed else 4,
                           f"Temporary access removal: {len(results) - failed} completed, {failed} failed.",
                           {"grant_id": normalized_id, "servers": results})
