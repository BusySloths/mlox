"""System and user-management helpers for Ubuntu executors."""

from __future__ import annotations

import logging
import os

from fabric import Connection  # type: ignore

from mlox.execution.base import TaskGroup, TaskRunnerABC

logger = logging.getLogger(__name__)


class SystemMixin(TaskRunnerABC):
    def sys_disk_free(self, connection: Connection) -> int:
        uname = (
            self._run_task(
                connection,
                group=TaskGroup.NETWORKING,
                command="uname -s",
            )
            or ""
        )
        if "Linux" in uname:
            perc = (
                self._run_task(
                    connection,
                    group=TaskGroup.NETWORKING,
                    command="df -h / | tail -n1 | awk '{print $5}'",
                )
                or "0%"
            )
            value = int(perc[:-1])
            return value
        logger.error("No idea how to get disk space on %s!", uname)
        return 0

    def sys_root_apt_install(
        self, connection: Connection, param: str, upgrade: bool = False
    ) -> str | None:
        cmd = "apt upgrade" if upgrade else f"apt install {param}"
        self._run_task(
            connection,
            group=TaskGroup.SYSTEM_PACKAGES,
            command="dpkg --configure -a",
        )
        result = self._run_task(
            connection,
            group=TaskGroup.SYSTEM_PACKAGES,
            command=cmd,
        )
        return result

    def sys_user_id(self, connection: Connection) -> str | None:
        result = self._run_task(
            connection,
            group=TaskGroup.USER_ACCESS,
            command="id -u",
            sudo=False,
        )
        return result

    def sys_list_user(self, connection: Connection) -> str | None:
        result = self._run_task(
            connection,
            group=TaskGroup.USER_ACCESS,
            command="ls -l /home | awk '{print $4}'",
            sudo=False,
        )
        return result

    def sys_add_user(
        self,
        connection: Connection,
        user_name: str,
        passwd: str,
        with_home_dir: bool = False,
        sudoer: bool = False,
    ) -> str | None:
        p_home_dir = "-m " if with_home_dir else ""
        command = f"useradd -p `openssl passwd {passwd}` {p_home_dir}-d /home/{user_name} {user_name}"
        result = self._run_task(
            connection,
            group=TaskGroup.USER_ACCESS,
            command=command,
            sudo=True,
        )
        if sudoer:
            self._run_task(
                connection,
                group=TaskGroup.USER_ACCESS,
                command=f"usermod -aG sudo {user_name}",
                sudo=True,
            )

            if os.environ.get("MLOX_DEBUG", False):
                logger.warning(
                    "[DEBUG ENABLED] sudoer group member do not need to pw anymore."
                )
                sudoer_file_content = f"{user_name} ALL=(ALL) NOPASSWD: ALL"
                sudoer_file_path = f"/etc/sudoers.d/90-mlox-{user_name}"
                self._run_task(
                    connection,
                    group=TaskGroup.USER_ACCESS,
                    command=f"echo '{sudoer_file_content}' | tee {sudoer_file_path}",
                    sudo=True,
                )
                self._run_task(
                    connection,
                    group=TaskGroup.USER_ACCESS,
                    command=f"chmod 440 {sudoer_file_path}",
                    sudo=True,
                )

        return result
