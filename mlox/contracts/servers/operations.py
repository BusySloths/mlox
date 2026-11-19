"""Server capability contracts."""

from abc import ABC, abstractmethod
from dataclasses import dataclass

from mlox.firewall import FirewallPolicy, FirewallPolicyRule, FirewallStatus


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
