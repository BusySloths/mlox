"""Declarative CLI contract for firewall operations."""

from mlox.cli.generation import CliParameter, WorkspaceCommand
from mlox.cli.rendering.results import render_inspection


FIREWALL_ACCESS_COMMANDS = (
    WorkspaceCommand(
        name="access-add", method="grant_firewall_access",
        help="Grant this computer temporary access to all active project firewalls.",
        parameters=(CliParameter("duration", "Access duration: 15m or 1h", default="15m"),),
        renderer=render_inspection, render_failure=True,
    ),
    WorkspaceCommand(
        name="access-remove", method="revoke_firewall_access",
        help="Remove this computer's temporary access from project firewalls.",
        renderer=render_inspection, render_failure=True,
    ),
)

FIREWALL_RULE_COMMANDS = (
    *(
        WorkspaceCommand(
            name=f"draft-{action}",
            method=f"{action}_firewall_draft_source",
            help=f"{action.capitalize()} a trusted IP or CIDR in the local draft; does not change the server.",
            parameters=(
                CliParameter("ip", "Server IP, unique suffix, or bundle name", kind="argument"),
                CliParameter("source", "Trusted IP address or CIDR", kind="argument"),
            ),
            renderer=render_inspection,
        )
        for action in ("add", "remove")
    ),
    WorkspaceCommand(
        name="preview", method="preview_server_firewall",
        help="Preview the proposed default firewall policy without changing the server.",
        parameters=(CliParameter("ip", "Server IP, unique suffix, or bundle name", kind="argument"),),
        renderer=render_inspection,
    ),
    WorkspaceCommand(
        name="apply", method="apply_server_firewall",
        help="Apply this server's firewall draft; rules may not persist after reboot.",
        parameters=(CliParameter("ip", "Server IP, unique suffix, or bundle name", kind="argument"),),
        renderer=render_inspection,
    ),
    WorkspaceCommand(
        name="persist", method="persist_server_firewall",
        help="Make the currently applied firewall draft survive server reboots.",
        parameters=(CliParameter("ip", "Server IP, unique suffix, or bundle name", kind="argument"),),
        renderer=render_inspection,
    ),
)
