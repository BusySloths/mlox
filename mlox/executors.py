"""Ubuntu-specific remote command helpers with execution history support.

This module is the public compatibility facade for executor imports. Domain
helpers live in ``mlox.execution`` mixins to keep the concrete executor small
while preserving existing ``UbuntuTaskExecutor`` call sites.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Dict, Optional

from fabric import Connection  # type: ignore

from mlox.execution.base import ExecutionRecorder, TaskGroup, _quote_command
from mlox.execution.docker import DockerMixin
from mlox.execution.filesystem import FilesystemMixin
from mlox.execution.firewall import FirewallMixin
from mlox.execution.git import GitMixin
from mlox.execution.kubernetes import KubernetesMixin
from mlox.execution.security import SecurityMixin
from mlox.execution.system import SystemMixin

logger = logging.getLogger(__name__)


@dataclass
class UbuntuTaskExecutor(
    SystemMixin,
    # FilesystemMixin must precede SecurityMixin so its concrete fs_* methods
    # satisfy SecurityMixin's abstract filesystem helper requirements.
    FilesystemMixin,
    SecurityMixin,
    KubernetesMixin,
    DockerMixin,
    FirewallMixin,
    GitMixin,
    ExecutionRecorder,
):
    """Execute Ubuntu-specific remote commands while recording history."""

    supported_os_ids: str = "Ubuntu"
    firewall_input_chain: str = "MLOX-FIREWALL"
    firewall_docker_chain: str = "MLOX-DOCKER-FIREWALL"
    security_global_disable_sudo: bool = False

    def _exec_command(
        self,
        connection: Connection,
        cmd: str,
        sudo: bool = False,
        pty: bool = False,
        *,
        action: str = "exec_command",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str | None:
        """Execute a command on the remote host and log the outcome."""

        hide = "stderr" if sudo else True
        metadata = metadata or {}
        metadata = {**metadata, "sudo": sudo, "pty": pty}
        try:
            if sudo and not self.security_global_disable_sudo:
                result = connection.sudo(cmd, hide=hide, pty=pty)
            else:
                result = connection.run(cmd, hide=hide)

            stdout = result.stdout.strip()
            self._record_history(
                action=action,
                status="success",
                command=cmd,
                exit_code=getattr(result, "exited", None),
                output=stdout,
                metadata=metadata,
            )
            return stdout
        except Exception as exc:
            self._record_history(
                action=action,
                status="error",
                command=cmd,
                error=str(exc),
                metadata=metadata,
            )
            if sudo:
                logger.error("Command failed: %s", exc)
                return None
            raise

    def execute(
        self,
        connection: Connection,
        command: str,
        *,
        group: TaskGroup,
        sudo: bool = False,
        pty: bool = False,
        description: str | None = None,
        extra_metadata: Optional[Dict[str, Any]] = None,
    ) -> str | None:
        """Public entry point to execute a grouped remote command."""

        return self._run_task(
            connection,
            group=group,
            command=command,
            sudo=sudo,
            pty=pty,
            description=description,
            extra_metadata=extra_metadata,
        )

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
        metadata: Dict[str, Any] = {"group": group.value}
        if description:
            metadata["description"] = description
        if extra_metadata:
            metadata.update(extra_metadata)
        return self._exec_command(
            connection,
            command,
            sudo=sudo,
            pty=pty,
            action=f"task:{group.value}",
            metadata=metadata,
        )


__all__ = [
    "ExecutionRecorder",
    "TaskGroup",
    "UbuntuTaskExecutor",
    "_quote_command",
]
