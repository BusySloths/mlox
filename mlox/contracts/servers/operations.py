"""Server capability contracts."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import ContextManager

from mlox.firewall import FirewallPolicy, FirewallPolicyRule, FirewallStatus
from mlox.firewall_grants import FirewallAccessGrant
from mlox.tunnel import TunnelBinding, TunnelEndpoint


class AbstractTunnelServer(ABC):
    @abstractmethod
    def open_tunnel(self, endpoint: TunnelEndpoint) -> ContextManager[TunnelBinding]:
        """Open a local-only forwarding context; closing it releases resources."""
        raise NotImplementedError


@dataclass
class AbstractGitServer(ABC):
    # GIT
    @abstractmethod
    def git_clone(self, repo_url: str, path: str) -> None:
        pass

    @abstractmethod
    def git_pull(self, path: str) -> None:
        pass

    @abstractmethod
    def git_remove(self, path: str) -> None:
        pass


@dataclass
class AbstractFirewallServer(ABC):
    def firewall_grant_current_client(self, grant_id: str, duration_seconds: int) -> FirewallAccessGrant | None:
        """Grant the observed SSH client temporary access, or skip an inactive firewall."""
        raise NotImplementedError("Temporary firewall access is not supported by this server.")

    def firewall_remove_client_grant(self, grant_id: str) -> None:
        """Remove one temporary grant without changing other grants or the policy."""
        raise NotImplementedError("Temporary firewall access is not supported by this server.")

    def firewall_list_client_grants(self) -> tuple[FirewallAccessGrant, ...]:
        """List active temporary grants without exposing the persistent policy."""
        raise NotImplementedError("Temporary firewall access is not supported by this server.")

    @abstractmethod
    def firewall_default_policy(self) -> FirewallPolicy:
        """Propose a policy appropriate for this server."""
        raise NotImplementedError

    @abstractmethod
    def firewall_validate_policy(self, policy: FirewallPolicy) -> None:
        """Reject a policy that cannot safely manage this server."""
        raise NotImplementedError

    @abstractmethod
    def firewall_policy_rules(self) -> tuple[FirewallPolicyRule, ...]:
        """Describe backend-specific fixed rules in the policy."""
        raise NotImplementedError

    @abstractmethod
    def firewall_persist_policy(self, policy: FirewallPolicy) -> None:
        """Persist an already applied policy, when supported by this server."""
        raise NotImplementedError("Policy persistence is not supported by this server.")

    @abstractmethod
    def firewall_apply_policy(self, policy: FirewallPolicy) -> None:
        """Apply a complete policy, when supported by this server."""
        raise NotImplementedError("Policy application is not supported by this server.")

    @abstractmethod
    def firewall_down(self) -> None:
        pass

    @abstractmethod
    def firewall_status(self) -> FirewallStatus:
        pass


@dataclass
class AbstractInitialPasswordAuthServer(ABC):
    @abstractmethod
    def add_mlox_user(self) -> None:
        pass

    @abstractmethod
    def setup_users(self) -> None:
        pass

    @abstractmethod
    def enable_password_authentication(self) -> None:
        pass

    @abstractmethod
    def disable_password_authentication(self) -> None:
        pass
