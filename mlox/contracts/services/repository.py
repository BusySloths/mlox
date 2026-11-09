"""Service capability contracts."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, ClassVar
from .capabilities import ServiceCapability


@dataclass
class AbstractRepositoryService(ABC):
    """Service capability mixin for repository provider services."""

    capabilities: ClassVar[set[ServiceCapability]] = {ServiceCapability.REPOSITORY}
    repo_name: str = field(default="", init=False)
    orchestrator_uuid: str | None = field(default=None, init=False)
    created_timestamp: str = field(default_factory=datetime.now().isoformat, init=False)
    modified_timestamp: str = field(
        default_factory=datetime.now().isoformat, init=False
    )

    @abstractmethod
    def get_url(self) -> str:
        pass

    @abstractmethod
    def git_clone(self, conn) -> None:
        pass

    @abstractmethod
    def git_pull(self, conn) -> None:
        pass

    def get_repository_root(self) -> str:
        """Return the absolute repository checkout root path when known."""

        target_path = str(getattr(self, "target_path", "") or "").rstrip("/")
        repo_name = str(getattr(self, "repo_name", "") or "").strip("/")
        if target_path and repo_name:
            return f"{target_path}/{repo_name}"
        return target_path or repo_name

    def repository_summary(self) -> dict[str, Any]:
        """Return non-IO metadata for repository overview screens."""

        deploy_keys = self.get_deploy_keys()
        return {
            "name": str(getattr(self, "repo_name", "") or getattr(self, "name", "-")),
            "url": self.get_url(),
            "root": self.get_repository_root(),
            "private": bool(getattr(self, "is_private", False)),
            "cloned": bool(getattr(self, "cloned", False)),
            "orchestrator_uuid": getattr(self, "orchestrator_uuid", None),
            "state": str(getattr(self, "state", "unknown")),
            "created": str(getattr(self, "created_timestamp", "") or ""),
            "modified": str(getattr(self, "modified_timestamp", "") or ""),
            "deploy_keys_available": bool(deploy_keys),
        }

    def get_deploy_keys(self) -> dict[str, str]:
        """Return deploy keys safe to show or copy in a UI."""

        return {}

    def list_repository_tree(self, conn) -> list[dict[str, Any]]:
        """List repository files for read-only browsing."""

        root = self.get_repository_root()
        if not root:
            return []
        return self.exec.fs_list_file_tree(conn, root)

    def read_repository_file(self, conn, path: str) -> str:
        """Read one repository file as text."""

        return str(self.exec.fs_read_file(conn, path, format="string"))
