"""Server capability contracts."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Mapping, Sequence


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
    def firewall_up(
        self,
        ports: Sequence[int] | Mapping[int, Sequence[str] | None],
        source_ips_by_port: Mapping[int, Sequence[str] | None] | None = None,
    ) -> None:
        pass

    @abstractmethod
    def firewall_down(self) -> None:
        pass

    @abstractmethod
    def firewall_status(self) -> str | None:
        pass

    @abstractmethod
    def firewall_update(
        self,
        ports: Sequence[int] | Mapping[int, Sequence[str] | None],
        source_ips_by_port: Mapping[int, Sequence[str] | None] | None = None,
    ) -> None:
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
