"""System and user-management helpers for Ubuntu executors."""

from __future__ import annotations

import logging
import os

from fabric import Connection  # type: ignore

from mlox.execution.base import TaskGroup, TaskRunnerABC

logger = logging.getLogger(__name__)


class SystemMixin(TaskRunnerABC):
    def sys_get_distro_info(self, connection: Connection) -> dict[str, str] | None:
        """
        Return Linux distribution metadata from /etc/os-release or lsb_release.
        """

        info: dict[str, str] = {}
        try:
            content = self.fs_read_file(  # type: ignore[attr-defined]
                connection, "/etc/os-release", format="string"
            )
            for line in content.strip().split("\n"):
                if "=" in line:
                    key, value = line.split("=", 1)
                    key = key.strip().lower()
                    value = value.strip().strip('"')
                    info[key] = value
            if "version_id" in info:
                info["version"] = info["version_id"]
            if "name" in info or "pretty_name" in info:
                logger.info("Distro info from /etc/os-release: %s", info)
                return info
        except Exception as exc:
            logger.warning(
                "Could not read /etc/os-release: %s. Trying lsb_release.", exc
            )
            info = {}

        try:
            lsb_output = self._run_task(
                connection,
                group=TaskGroup.NETWORKING,
                command="lsb_release -a",
                sudo=False,
                pty=False,
            )
            if lsb_output:
                for line in lsb_output.strip().split("\n"):
                    if ":" in line:
                        key, value = line.split(":", 1)
                        key = key.strip().lower().replace(" ", "_")
                        value = value.strip()
                        if key == "distributor_id":
                            info["id"] = value
                            info["name"] = value
                        if key == "release":
                            info["version"] = value
                        if key == "description":
                            info["pretty_name"] = value
                        if key == "codename":
                            info["codename"] = value
                if "name" in info and "version" in info:
                    logger.info("Distro info from lsb_release: %s", info)
                    return info
        except Exception as exc:
            logger.error("Could not get distro info using lsb_release: %s", exc)

        logger.error("Unable to determine Linux distribution info.")
        return None

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
