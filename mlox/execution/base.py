"""Shared execution primitives for remote task executors."""

from __future__ import annotations

import shlex
from abc import ABC, abstractmethod
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Deque, Dict, Iterable, Optional

from fabric import Connection  # type: ignore


def _quote_command(parts: Iterable[str]) -> str:
    return " ".join(shlex.quote(part) for part in parts)


class TaskGroup(Enum):
    """Logical buckets describing the type of remote action being executed."""

    SYSTEM_PACKAGES = "system_packages"
    SERVICE_CONTROL = "service_control"
    CONTAINER_RUNTIME = "container_runtime"
    KUBERNETES = "kubernetes"
    FILESYSTEM = "filesystem"
    USER_ACCESS = "user_access"
    SECURITY_ASSETS = "security_assets"
    VERSION_CONTROL = "version_control"
    NETWORKING = "networking"
    AD_HOC = "ad_hoc"


class TaskRunnerABC(ABC):
    """Minimal host contract expected by executor mixins."""

    @abstractmethod
    def _run_task(
        self,
        connection: Connection,
        *,
        group: TaskGroup,
        command: str,
        sudo: bool = False,
        pty: bool = False,
        description: str | None = None,
        extra_metadata: Optional[Dict[str, Any]] = None,
    ) -> str | None:
        raise NotImplementedError


class FilesystemTaskRunnerABC(TaskRunnerABC):
    """Host contract for mixins that need filesystem helpers."""

    @abstractmethod
    def fs_copy(self, connection: Connection, src_file: str, dst_path: str) -> None:
        raise NotImplementedError

    @abstractmethod
    def fs_create_dir(self, connection: Connection, path: str) -> None:
        raise NotImplementedError

    @abstractmethod
    def fs_find_and_replace(
        self,
        connection: Connection,
        fname: str,
        old: str,
        new: str,
        *,
        separator: str = "!",
        sudo: bool = False,
    ) -> None:
        raise NotImplementedError


@dataclass
class ExecutionRecorder:
    """Base class providing chronological execution history recording."""

    history_limit: int = 200
    history_data: list[dict[str, Any]] = field(default_factory=list, repr=False)

    def __post_init__(self) -> None:
        # keep a deque for fast append/pop operations during runtime
        # but store as list for serialization (deque is not json serializable)
        history_deque: Deque[dict[str, Any]] = deque(
            self.history_data, maxlen=self.history_limit
        )
        object.__setattr__(self, "_history", history_deque)

    def _record_history(
        self,
        *,
        action: str,
        status: str,
        command: str | None = None,
        exit_code: int | None = None,
        output: str | None = None,
        error: str | None = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "action": action,
            "status": status,
        }

        if command is not None:
            entry["command"] = command
        if exit_code is not None:
            entry["exit_code"] = exit_code
        if output is not None:
            entry["output"] = output
        if error is not None:
            entry["error"] = error
        if metadata:
            entry["metadata"] = metadata

        self._history.append(entry)
        self.history_data = list(self._history)
        # logger.debug("Recorded history entry: %s", entry)

    @property
    def history(self) -> Iterable[dict[str, Any]]:
        """Return a snapshot of the execution history."""
        return list(self._history)
