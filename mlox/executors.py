"""Ubuntu-specific remote command helpers with execution history support."""

from __future__ import annotations

import json
import logging
import os
import re
import secrets
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from io import BytesIO
from typing import Any, Deque, Dict, Iterable, Optional

import yaml
from fabric import Connection  # type: ignore

logger = logging.getLogger(__name__)


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


@dataclass
class UbuntuTaskExecutor(ExecutionRecorder):
    """Execute Ubuntu-specific remote commands while recording history."""

    supported_os_ids: str = "Ubuntu"

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
            if sudo:
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

    # Task helpers ------------------------------------------------------

    def run_system_package_task(
        self,
        connection: Connection,
        command: str,
        *,
        sudo: bool = True,
        pty: bool = False,
        description: str | None = None,
        extra_metadata: Optional[Dict[str, Any]] = None,
    ) -> str | None:
        return self._run_task(
            connection,
            group=TaskGroup.SYSTEM_PACKAGES,
            command=command,
            sudo=sudo,
            pty=pty,
            description=description,
            extra_metadata=extra_metadata,
        )

    def run_service_task(
        self,
        connection: Connection,
        command: str,
        *,
        sudo: bool = True,
        pty: bool = False,
        description: str | None = None,
        extra_metadata: Optional[Dict[str, Any]] = None,
    ) -> str | None:
        return self._run_task(
            connection,
            group=TaskGroup.SERVICE_CONTROL,
            command=command,
            sudo=sudo,
            pty=pty,
            description=description,
            extra_metadata=extra_metadata,
        )

    def run_container_task(
        self,
        connection: Connection,
        command: str,
        *,
        sudo: bool = True,
        pty: bool = False,
        description: str | None = None,
        extra_metadata: Optional[Dict[str, Any]] = None,
    ) -> str | None:
        return self._run_task(
            connection,
            group=TaskGroup.CONTAINER_RUNTIME,
            command=command,
            sudo=sudo,
            pty=pty,
            description=description,
            extra_metadata=extra_metadata,
        )

    def run_kubernetes_task(
        self,
        connection: Connection,
        command: str,
        *,
        sudo: bool = True,
        pty: bool = False,
        description: str | None = None,
        extra_metadata: Optional[Dict[str, Any]] = None,
    ) -> str | None:
        return self._run_task(
            connection,
            group=TaskGroup.KUBERNETES,
            command=command,
            sudo=sudo,
            pty=pty,
            description=description,
            extra_metadata=extra_metadata,
        )

    def run_filesystem_task(
        self,
        connection: Connection,
        command: str,
        *,
        sudo: bool = False,
        pty: bool = False,
        description: str | None = None,
        extra_metadata: Optional[Dict[str, Any]] = None,
    ) -> str | None:
        return self._run_task(
            connection,
            group=TaskGroup.FILESYSTEM,
            command=command,
            sudo=sudo,
            pty=pty,
            description=description,
            extra_metadata=extra_metadata,
        )

    def run_user_task(
        self,
        connection: Connection,
        command: str,
        *,
        sudo: bool = True,
        pty: bool = False,
        description: str | None = None,
        extra_metadata: Optional[Dict[str, Any]] = None,
    ) -> str | None:
        return self._run_task(
            connection,
            group=TaskGroup.USER_ACCESS,
            command=command,
            sudo=sudo,
            pty=pty,
            description=description,
            extra_metadata=extra_metadata,
        )

    def run_security_task(
        self,
        connection: Connection,
        command: str,
        *,
        sudo: bool = False,
        pty: bool = False,
        description: str | None = None,
        extra_metadata: Optional[Dict[str, Any]] = None,
    ) -> str | None:
        return self._run_task(
            connection,
            group=TaskGroup.SECURITY_ASSETS,
            command=command,
            sudo=sudo,
            pty=pty,
            description=description,
            extra_metadata=extra_metadata,
        )

    def run_version_control_task(
        self,
        connection: Connection,
        command: str,
        *,
        sudo: bool = False,
        pty: bool = False,
        description: str | None = None,
        extra_metadata: Optional[Dict[str, Any]] = None,
    ) -> str | None:
        return self._run_task(
            connection,
            group=TaskGroup.VERSION_CONTROL,
            command=command,
            sudo=sudo,
            pty=pty,
            description=description,
            extra_metadata=extra_metadata,
        )

    def run_network_task(
        self,
        connection: Connection,
        command: str,
        *,
        sudo: bool = False,
        pty: bool = False,
        description: str | None = None,
        extra_metadata: Optional[Dict[str, Any]] = None,
    ) -> str | None:
        return self._run_task(
            connection,
            group=TaskGroup.NETWORKING,
            command=command,
            sudo=sudo,
            pty=pty,
            description=description,
            extra_metadata=extra_metadata,
        )

    def run_ad_hoc_task(
        self,
        connection: Connection,
        command: str,
        *,
        sudo: bool = False,
        pty: bool = False,
        description: str | None = None,
        extra_metadata: Optional[Dict[str, Any]] = None,
    ) -> str | None:
        return self._run_task(
            connection,
            group=TaskGroup.AD_HOC,
            command=command,
            sudo=sudo,
            pty=pty,
            description=description,
            extra_metadata=extra_metadata,
        )

    def sys_disk_free(self, connection: Connection) -> int:
        uname = self.run_network_task(connection, "uname -s") or ""
        if "Linux" in uname:
            perc = (
                self.run_network_task(
                    connection, "df -h / | tail -n1 | awk '{print $5}'"
                )
                or "0%"
            )
            value = int(perc[:-1])
            self._record_history(
                action="sys_disk_free", status="success", output=str(value)
            )
            return value
        self._record_history(action="sys_disk_free", status="error", output=uname)
        logger.error("No idea how to get disk space on %s!", uname)
        return 0

    def sys_root_apt_install(
        self, connection: Connection, param: str, upgrade: bool = False
    ) -> str | None:
        cmd = "apt upgrade" if upgrade else f"apt install {param}"
        self.run_system_package_task(connection, "dpkg --configure -a")
        result = self.run_system_package_task(connection, cmd)
        self._record_history(
            action="sys_root_apt_install",
            status="success",
            command=cmd,
            output=result,
            metadata={"upgrade": upgrade},
        )
        return result

    def sys_user_id(self, connection: Connection) -> str | None:
        result = self.run_user_task(connection, "id -u", sudo=False)
        self._record_history(action="sys_user_id", status="success", output=result)
        return result

    def sys_list_user(self, connection: Connection) -> str | None:
        result = self.run_user_task(
            connection,
            "ls -l /home | awk '{print $4}'",
            sudo=False,
        )
        self._record_history(action="sys_list_user", status="success", output=result)
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
        result = self.run_user_task(connection, command, sudo=True)
        if sudoer:
            self.run_user_task(
                connection, f"usermod -aG sudo {user_name}", sudo=True
            )

            if os.environ.get("MLOX_DEBUG", False):
                logger.warning(
                    "[DEBUG ENABLED] sudoer group member do not need to pw anymore."
                )
                sudoer_file_content = f"{user_name} ALL=(ALL) NOPASSWD: ALL"
                sudoer_file_path = f"/etc/sudoers.d/90-mlox-{user_name}"
                self.run_user_task(
                    connection,
                    f"echo '{sudoer_file_content}' | tee {sudoer_file_path}",
                    sudo=True,
                )
                self.run_user_task(
                    connection, f"chmod 440 {sudoer_file_path}", sudo=True
                )

        self._record_history(
            action="sys_add_user",
            status="success",
            command=command,
            output=result,
            metadata={
                "user_name": user_name,
                "with_home_dir": with_home_dir,
                "sudoer": sudoer,
            },
        )
        return result

    def _get_stacks_path(self) -> str:
        """Return the default path containing stack configuration files."""

        # This preserves the historical behaviour of referencing the local
        # stacks directory without relying on importlib.resources which may
        # not always be available in runtime environments (e.g. when running
        # from a source checkout during development).
        return "./mlox/stacks/mlox"

    def tls_setup_no_config(self, connection: Connection, ip: str, path: str) -> None:
        """Create TLS assets on the remote host without using a custom config."""

        self.fs_create_dir(connection, path)

        subject = f"/CN={ip}"

        self.run_security_task(
            connection, f"cd {path}; openssl genrsa -out key.pem 2048"
        )
        self.run_security_task(
            connection,
            f"cd {path}; openssl req -new -key key.pem -out server.csr -subj '{subject}'",
        )
        self.run_security_task(
            connection,
            (
                f"cd {path}; "
                "openssl x509 -req -in server.csr -signkey key.pem -out cert.pem "
                "-days 365"
            ),
        )
        self.run_security_task(
            connection, f"chmod u=rw,g=rw,o=rw {path}/key.pem"
        )
        self.run_security_task(
            connection, f"chmod u=rw,g=rw,o=rw {path}/cert.pem"
        )

        self._record_history(
            action="tls_setup_no_config",
            status="success",
            metadata={"ip": ip, "path": path},
        )

    def tls_setup(self, connection: Connection, ip: str, path: str) -> None:
        """Create TLS assets on the remote host using an OpenSSL config."""

        self.fs_create_dir(connection, path)

        stacks_path = self._get_stacks_path()
        self.fs_copy(connection, f"{stacks_path}/openssl-san.cnf", f"{path}/openssl-san.cnf")
        self.fs_find_and_replace(
            connection, f"{path}/openssl-san.cnf", "<MY_IP>", f"{ip}"
        )

        self.run_security_task(
            connection, f"cd {path}; openssl genrsa -out key.pem 2048"
        )
        self.run_security_task(
            connection,
            f"cd {path}; openssl req -new -key key.pem -out server.csr -config openssl-san.cnf",
        )
        cmd = (
            f"cd {path}; "
            "openssl x509 -req -in server.csr -signkey key.pem "
            "-out cert.pem -days 365 -extensions req_ext -extfile openssl-san.cnf"
        )
        self.run_security_task(connection, cmd)
        self.run_security_task(
            connection, f"chmod u=rw,g=rw,o=rw {path}/key.pem"
        )

        self._record_history(
            action="tls_setup",
            status="success",
            metadata={"ip": ip, "path": path},
        )

    def docker_list_container(self, connection: Connection) -> list[list[str]]:
        res = (
            self.run_container_task(connection, "docker container ls", sudo=True) or ""
        )
        dl = str(res).split("\n")
        dlist = [re.sub(r"\ {2,}", "    ", dl[i]).split("   ") for i in range(len(dl))]
        self._record_history(
            action="docker_list_container", status="success", output=str(dlist)
        )
        return dlist

    def docker_down(
        self,
        connection: Connection,
        config_yaml: str,
        remove_volumes: bool = False,
    ) -> str | None:
        volumes = "--volumes " if remove_volumes else ""
        command = f'docker compose -f "{config_yaml}" down {volumes}--remove-orphans'
        result = self.run_container_task(connection, command, sudo=True)
        self._record_history(
            action="docker_down",
            status="success",
            command=command,
            output=result,
            metadata={"remove_volumes": remove_volumes},
        )
        return result

    def docker_up(
        self,
        connection: Connection,
        config_yaml: str,
        env_file: str | None = None,
    ) -> str | None:
        command = f'docker compose -f "{config_yaml}" up -d --build'
        if env_file is not None:
            command = (
                f'docker compose --env-file {env_file} -f "{config_yaml}" up -d --build'
            )
        result = self.run_container_task(connection, command, sudo=True)
        self._record_history(
            action="docker_up",
            status="success",
            command=command,
            output=result,
            metadata={"env_file": env_file},
        )
        return result

    def docker_service_state(self, connection: Connection, service_name: str) -> str:
        cmd = f"docker inspect --format '{{{{.State.Status}}}}' {service_name}"
        res = (
            self.run_container_task(connection, cmd, sudo=True, pty=False) or ""
        )
        self._record_history(
            action="docker_service_state",
            status="success",
            command=cmd,
            output=res,
            metadata={"service_name": service_name},
        )
        return res

    def docker_all_service_states(
        self, connection: Connection
    ) -> dict[str, dict[Any, Any]]:
        ids = self.run_container_task(
            connection, "docker ps -aq", sudo=True, pty=False
        )
        if not ids:
            self._record_history(
                action="docker_all_service_states", status="success", output="{}"
            )
            return {}

        id_list = " ".join(ids.split())
        inspect_output = self.run_container_task(
            connection, f"docker inspect {id_list}", sudo=True, pty=False
        )
        try:
            containers = json.loads(inspect_output or "[]")
            result = {
                c.get("Name", "").lstrip("/"): c.get("State", {}) for c in containers
            }
            self._record_history(
                action="docker_all_service_states",
                status="success",
                output=json.dumps(result),
            )
            return result
        except Exception as exc:  # pragma: no cover - defensive
            self._record_history(
                action="docker_all_service_states",
                status="error",
                error=str(exc),
            )
            logger.warning("Failed to parse docker state info: %s", exc)
            return {}

    def docker_service_log_tails(
        self, connection: Connection, service_name: str, tail: int = 200
    ) -> str:
        try:
            cmd = f"docker logs --tail {int(tail)} {service_name}"
            res = (
                self.run_container_task(connection, cmd, sudo=True, pty=False)
                or "No docker logs found"
            )
            self._record_history(
                action="docker_service_log_tails",
                status="success",
                command=cmd,
                output=res,
                metadata={"tail": tail, "service_name": service_name},
            )
            return res
        except Exception as exc:  # pragma: no cover - defensive
            self._record_history(
                action="docker_service_log_tails",
                status="error",
                error=str(exc),
                metadata={"tail": tail, "service_name": service_name},
            )
            logger.warning("Failed to fetch logs for %s: %s", service_name, exc)
            return "Failed to fetch logs"

    def git_clone(
        self, connection: Connection, repo_url: str, install_path: str
    ) -> None:
        try:
            self.run_filesystem_task(connection, f"mkdir -p {install_path}")
            self.run_version_control_task(
                connection, f"cd {install_path}; git clone {repo_url}"
            )
            self._record_history(
                action="git_clone",
                status="success",
                metadata={"repo_url": repo_url, "install_path": install_path},
            )
        except Exception as exc:  # pragma: no cover - defensive
            self._record_history(
                action="git_clone",
                status="error",
                error=str(exc),
                metadata={"repo_url": repo_url, "install_path": install_path},
            )
            raise

    def fs_copy(self, connection: Connection, src_file: str, dst_path: str) -> None:
        try:
            connection.put(src_file, dst_path)
            self._record_history(
                action="fs_copy",
                status="success",
                metadata={"src_file": src_file, "dst_path": dst_path},
            )
        except Exception as exc:  # pragma: no cover - defensive
            self._record_history(
                action="fs_copy",
                status="error",
                error=str(exc),
                metadata={"src_file": src_file, "dst_path": dst_path},
            )
            raise

    def fs_create_dir(self, connection: Connection, path: str) -> None:
        self.run_filesystem_task(connection, f"mkdir -p {path}")
        self._record_history(
            action="fs_create_dir", status="success", metadata={"path": path}
        )

    def fs_delete_dir(self, connection: Connection, path: str) -> None:
        self.run_filesystem_task(connection, f"rm -rf {path}", sudo=True)
        self._record_history(
            action="fs_delete_dir", status="success", metadata={"path": path}
        )

    def fs_copy_dir(
        self,
        connection: Connection,
        src_path: str,
        dst_path: str,
        sudo: bool = False,
    ) -> None:
        self.run_filesystem_task(
            connection, f"cp -r {src_path} {dst_path}", sudo=sudo
        )
        self._record_history(
            action="fs_copy_dir",
            status="success",
            metadata={"src_path": src_path, "dst_path": dst_path, "sudo": sudo},
        )

    def fs_exists_dir(self, connection: Connection, path: str) -> bool:
        try:
            res = self.run_filesystem_task(
                connection, f"test -d {path} && echo exists || echo missing"
            )
            exists = str(res).strip() == "exists"
            self._record_history(
                action="fs_exists_dir",
                status="success",
                metadata={"path": path, "exists": exists},
            )
            return exists
        except Exception as exc:  # pragma: no cover - defensive
            self._record_history(
                action="fs_exists_dir",
                status="error",
                error=str(exc),
                metadata={"path": path},
            )
            return False

    def fs_create_symlink(
        self,
        connection: Connection,
        target_path: str,
        link_path: str,
        sudo: bool = False,
    ) -> None:
        self.run_filesystem_task(
            connection, f"ln -s {target_path} {link_path}", sudo=sudo
        )
        self._record_history(
            action="fs_create_symlink",
            status="success",
            metadata={
                "target_path": target_path,
                "link_path": link_path,
                "sudo": sudo,
            },
        )

    def fs_remove_symlink(
        self, connection: Connection, link_path: str, sudo: bool = False
    ) -> None:
        self.run_filesystem_task(connection, f"rm {link_path}", sudo=sudo)
        self._record_history(
            action="fs_remove_symlink",
            status="success",
            metadata={"link_path": link_path, "sudo": sudo},
        )

    def fs_touch(self, connection: Connection, fname: str) -> None:
        self.run_filesystem_task(connection, f"touch {fname}")
        self._record_history(
            action="fs_touch", status="success", metadata={"file": fname}
        )

    def fs_append_line(self, connection: Connection, fname: str, line: str) -> None:
        self.run_filesystem_task(connection, f"touch {fname}")
        self.run_filesystem_task(connection, f"echo '{line}' >> {fname}")
        self._record_history(
            action="fs_append_line",
            status="success",
            metadata={"file": fname, "line": line},
        )

    def fs_create_empty_file(self, connection: Connection, fname: str) -> None:
        self.run_filesystem_task(connection, f"echo -n >| {fname}")
        self._record_history(
            action="fs_create_empty_file", status="success", metadata={"file": fname}
        )

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
        self.run_filesystem_task(
            connection,
            f"sed -i 's{separator}{old}{separator}{new}{separator}g' {fname}",
            sudo=sudo,
        )
        self._record_history(
            action="fs_find_and_replace",
            status="success",
            metadata={
                "file": fname,
                "old": old,
                "new": new,
                "separator": separator,
                "sudo": sudo,
            },
        )

    def fs_write_file(
        self,
        connection: Connection,
        file_path: str,
        content: str | bytes,
        *,
        sudo: bool = False,
        encoding: str = "utf-8",
    ) -> None:
        if isinstance(content, str):
            content_bytes = content.encode(encoding)
        elif isinstance(content, bytes):
            content_bytes = content
        else:
            raise TypeError("Content must be str or bytes")

        file_like_object = BytesIO(content_bytes)

        if not sudo:
            connection.put(file_like_object, remote=file_path)
            logger.info("Wrote content to %s as user %s", file_path, connection.user)
        else:
            random_suffix = secrets.token_hex(8)
            remote_tmp_path = os.path.join("/tmp", f"mlox_tmp_{random_suffix}")

            try:
                connection.put(file_like_object, remote=remote_tmp_path)
                logger.info(
                    "Uploaded content to temporary remote path: %s", remote_tmp_path
                )
                self.run_filesystem_task(
                    connection, f"mv {remote_tmp_path} {file_path}", sudo=True
                )
                logger.info(
                    "Moved temporary file from %s to %s using sudo.",
                    remote_tmp_path,
                    file_path,
                )
            except Exception as exc:  # pragma: no cover - defensive
                logger.error("Error writing file %s with sudo: %s", file_path, exc)
                if connection.is_connected:
                    self.run_filesystem_task(
                        connection,
                        f"rm -f {remote_tmp_path}",
                        sudo=True,
                        pty=False,
                    )
                self._record_history(
                    action="fs_write_file",
                    status="error",
                    metadata={
                        "file_path": file_path,
                        "sudo": sudo,
                        "encoding": encoding,
                    },
                    error=str(exc),
                )
                raise

        self._record_history(
            action="fs_write_file",
            status="success",
            metadata={
                "file_path": file_path,
                "sudo": sudo,
                "encoding": encoding,
            },
        )

    def fs_read_file(
        self,
        connection: Connection,
        file_path: str,
        *,
        encoding: str = "utf-8",
        format: str = "yaml",
    ) -> Any:
        io_obj = BytesIO()
        connection.get(file_path, io_obj)
        data: Any
        if format == "yaml":
            data = yaml.safe_load(io_obj.getvalue())
        else:
            data = io_obj.getvalue().decode(encoding)
        self._record_history(
            action="fs_read_file",
            status="success",
            metadata={"file_path": file_path, "format": format, "encoding": encoding},
        )
        return data

    def fs_list_files(
        self, connection: Connection, path: str, sudo: bool = False
    ) -> list[str]:
        command = f"ls -A1 {path}"
        output = (
            self.run_filesystem_task(connection, command, sudo=sudo, pty=False) or ""
        )
        entries = output.splitlines() if output else []
        self._record_history(
            action="fs_list_files",
            status="success",
            command=command,
            metadata={"path": path, "sudo": sudo},
            output="\n".join(entries),
        )
        return entries

    def fs_list_file_tree(
        self, connection: Connection, path: str, sudo: bool = False
    ) -> list[dict[str, Any]]:
        command = f"find {path} -printf '%p|%y|%s|%TY-%Tm-%Td %TH:%TM:%TS\\n'"
        output = (
            self.run_filesystem_task(connection, command, sudo=sudo, pty=False) or ""
        )
        entries: list[dict[str, Any]] = []
        if output:
            for line in output.splitlines():
                try:
                    p, y, s, mdt = line.split("|", 3)
                    entry = {
                        "name": os.path.basename(p),
                        "path": p,
                        "is_file": y == "f",
                        "is_dir": y == "d",
                        "size": int(s),
                        "modification_datetime": mdt.split(".")[0],
                    }
                    entries.append(entry)
                except Exception as exc:  # pragma: no cover - defensive
                    logger.warning("Error parsing file tree line: %s (%s)", line, exc)

        self._record_history(
            action="fs_list_file_tree",
            status="success",
            command=command,
            metadata={"path": path, "sudo": sudo},
            output=json.dumps(entries),
        )
        return entries
