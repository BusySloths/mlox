"""Ubuntu-specific remote command helpers with execution history support."""

from __future__ import annotations

import json
import logging
import os
import re
import secrets
import shlex
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from io import BytesIO
from typing import Any, Deque, Dict, Iterable, Mapping, Optional, Sequence

import yaml
from fabric import Connection  # type: ignore

logger = logging.getLogger(__name__)


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

    def sys_disk_free(self, connection: Connection) -> int:
        uname = self._run_task(
            connection,
            group=TaskGroup.NETWORKING,
            command="uname -s",
        ) or ""
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

        self._run_task(
            connection,
            group=TaskGroup.SECURITY_ASSETS,
            command=f"cd {path}; openssl genrsa -out key.pem 2048",
        )
        self._run_task(
            connection,
            group=TaskGroup.SECURITY_ASSETS,
            command=(
                f"cd {path}; openssl req -new -key key.pem -out server.csr -subj '{subject}'"
            ),
        )
        self._run_task(
            connection,
            group=TaskGroup.SECURITY_ASSETS,
            command=(
                f"cd {path}; "
                "openssl x509 -req -in server.csr -signkey key.pem -out cert.pem "
                "-days 365"
            ),
        )
        self._run_task(
            connection,
            group=TaskGroup.SECURITY_ASSETS,
            command=f"chmod u=rw,g=rw,o=rw {path}/key.pem",
        )
        self._run_task(
            connection,
            group=TaskGroup.SECURITY_ASSETS,
            command=f"chmod u=rw,g=rw,o=rw {path}/cert.pem",
        )


    def tls_setup(self, connection: Connection, ip: str, path: str) -> None:
        """Create TLS assets on the remote host using an OpenSSL config."""

        self.fs_create_dir(connection, path)

        stacks_path = self._get_stacks_path()
        self.fs_copy(connection, f"{stacks_path}/openssl-san.cnf", f"{path}/openssl-san.cnf")
        self.fs_find_and_replace(
            connection, f"{path}/openssl-san.cnf", "<MY_IP>", f"{ip}"
        )

        self._run_task(
            connection,
            group=TaskGroup.SECURITY_ASSETS,
            command=f"cd {path}; openssl genrsa -out key.pem 2048",
        )
        self._run_task(
            connection,
            group=TaskGroup.SECURITY_ASSETS,
            command=(
                f"cd {path}; openssl req -new -key key.pem -out server.csr -config openssl-san.cnf"
            ),
        )
        cmd = (
            f"cd {path}; "
            "openssl x509 -req -in server.csr -signkey key.pem "
            "-out cert.pem -days 365 -extensions req_ext -extfile openssl-san.cnf"
        )
        self._run_task(
            connection,
            group=TaskGroup.SECURITY_ASSETS,
            command=cmd,
        )
        self._run_task(
            connection,
            group=TaskGroup.SECURITY_ASSETS,
            command=f"chmod u=rw,g=rw,o=rw {path}/key.pem",
        )


    def security_generate_ssh_key(
        self,
        connection: Connection,
        *,
        key_path: str,
        key_type: str = "rsa",
        bits: int = 4096,
        comment: str | None = None,
        sudo: bool = False,
        overwrite: bool = True,
    ) -> None:
        if overwrite:
            cleanup_cmd = _quote_command(
                [
                    "rm",
                    "-f",
                    key_path,
                    f"{key_path}.pub",
                ]
            )
            self._run_task(
                connection,
                group=TaskGroup.SECURITY_ASSETS,
                command=cleanup_cmd,
                sudo=sudo,
            )
        parts: list[str] = [
            "ssh-keygen",
            "-q",
            "-t",
            key_type,
            "-b",
            str(bits),
            "-N",
            "",
            "-f",
            key_path,
        ]
        if comment:
            parts.extend(["-C", comment])
        command = _quote_command(parts)
        self._run_task(
            connection,
            group=TaskGroup.SECURITY_ASSETS,
            command=command,
            sudo=sudo,
        )

    def helm_repo_add(
        self,
        connection: Connection,
        name: str,
        url: str,
        *,
        kubeconfig: str | None = None,
        sudo: bool = True,
    ) -> str | None:
        parts = ["helm", "repo", "add", name, url]
        if kubeconfig:
            parts.extend(["--kubeconfig", kubeconfig])
        command = _quote_command(parts)
        result = self._run_task(
            connection,
            group=TaskGroup.KUBERNETES,
            command=command,
            sudo=sudo,
        )
        return result

    def helm_repo_update(
        self,
        connection: Connection,
        *,
        repo: str | None = None,
        kubeconfig: str | None = None,
        sudo: bool = True,
    ) -> str | None:
        parts = ["helm", "repo", "update"]
        if repo:
            parts.append(repo)
        if kubeconfig:
            parts.extend(["--kubeconfig", kubeconfig])
        command = _quote_command(parts)
        result = self._run_task(
            connection,
            group=TaskGroup.KUBERNETES,
            command=command,
            sudo=sudo,
        )
        return result

    def helm_upgrade_install(
        self,
        connection: Connection,
        *,
        release: str,
        chart: str,
        namespace: str,
        kubeconfig: str | None = None,
        create_namespace: bool = False,
        values: Mapping[str, str] | None = None,
        extra_args: Sequence[str] | None = None,
        sudo: bool = True,
    ) -> str | None:
        parts: list[str] = ["helm", "upgrade", "--install", release, chart]
        parts.extend(["--namespace", namespace])
        if create_namespace:
            parts.append("--create-namespace")
        if kubeconfig:
            parts.extend(["--kubeconfig", kubeconfig])
        if values:
            for key, value in values.items():
                parts.extend(["--set", f"{key}={value}"])
        if extra_args:
            parts.extend(extra_args)
        command = _quote_command(parts)
        result = self._run_task(
            connection,
            group=TaskGroup.KUBERNETES,
            command=command,
            sudo=sudo,
        )
        return result

    def helm_uninstall(
        self,
        connection: Connection,
        *,
        release: str,
        namespace: str,
        kubeconfig: str | None = None,
        extra_args: Sequence[str] | None = None,
        sudo: bool = True,
        ignore_missing: bool = False,
    ) -> str | None:
        parts: list[str] = ["helm", "uninstall", release, "--namespace", namespace]
        if kubeconfig:
            parts.extend(["--kubeconfig", kubeconfig])
        if extra_args:
            parts.extend(extra_args)
        command = _quote_command(parts)
        try:
            result = self._run_task(
                connection,
                group=TaskGroup.KUBERNETES,
                command=command,
                sudo=sudo,
            )
            status = "success"
            error: str | None = None
        except Exception as exc:
            if not ignore_missing:
                raise
            result = None
            status = "warning"
            error = str(exc)
        return result

    def helm_status(
        self,
        connection: Connection,
        *,
        release: str,
        namespace: str,
        kubeconfig: str | None = None,
        output_format: str | None = None,
        sudo: bool = True,
    ) -> str | None:
        parts: list[str] = ["helm", "status", release, "--namespace", namespace]
        if kubeconfig:
            parts.extend(["--kubeconfig", kubeconfig])
        if output_format:
            parts.extend(["-o", output_format])
        command = _quote_command(parts)
        result = self._run_task(
            connection,
            group=TaskGroup.KUBERNETES,
            command=command,
            sudo=sudo,
        )
        return result

    def k8s_create_token(
        self,
        connection: Connection,
        *,
        service_account: str,
        namespace: str,
        kubeconfig: str | None = None,
        sudo: bool = True,
    ) -> str | None:
        parts: list[str] = ["kubectl", "create", "token", service_account, "--namespace", namespace]
        if kubeconfig:
            parts.extend(["--kubeconfig", kubeconfig])
        command = _quote_command(parts)
        result = self._run_task(
            connection,
            group=TaskGroup.KUBERNETES,
            command=command,
            sudo=sudo,
        )
        return result

    def k8s_namespace_exists(
        self,
        connection: Connection,
        namespace: str,
        *,
        kubeconfig: str | None = None,
        sudo: bool = True,
    ) -> bool:
        parts: list[str] = [
            "kubectl",
            "get",
            "namespace",
            namespace,
            "--ignore-not-found",
            "--output",
            "name",
        ]
        if kubeconfig:
            parts.extend(["--kubeconfig", kubeconfig])
        command = _quote_command(parts)
        output = self._run_task(
            connection,
            group=TaskGroup.KUBERNETES,
            command=command,
            sudo=sudo,
        )
        exists = bool(output and output.strip())
        return exists

    def k8s_apply_manifest(
        self,
        connection: Connection,
        manifest: str,
        *,
        namespace: str | None = None,
        kubeconfig: str | None = None,
        sudo: bool = True,
    ) -> str | None:
        parts: list[str] = ["kubectl", "apply", "-f", manifest]
        if namespace:
            parts.extend(["--namespace", namespace])
        if kubeconfig:
            parts.extend(["--kubeconfig", kubeconfig])
        command = _quote_command(parts)
        result = self._run_task(
            connection,
            group=TaskGroup.KUBERNETES,
            command=command,
            sudo=sudo,
        )
        return result

    def k8s_patch_resource(
        self,
        connection: Connection,
        resource_type: str,
        name: str,
        patch: Mapping[str, Any] | str,
        *,
        namespace: str | None = None,
        kubeconfig: str | None = None,
        patch_type: str = "merge",
        sudo: bool = True,
    ) -> str | None:
        if isinstance(patch, Mapping):
            patch_payload = json.dumps(patch)
        else:
            patch_payload = patch
        parts: list[str] = [
            "kubectl",
            "patch",
            resource_type,
            name,
            "--type",
            patch_type,
            "-p",
            patch_payload,
        ]
        if namespace:
            parts.extend(["--namespace", namespace])
        if kubeconfig:
            parts.extend(["--kubeconfig", kubeconfig])
        command = _quote_command(parts)
        result = self._run_task(
            connection,
            group=TaskGroup.KUBERNETES,
            command=command,
            sudo=sudo,
        )
        return result

    def k8s_delete_manifest(
        self,
        connection: Connection,
        manifest: str,
        *,
        namespace: str | None = None,
        kubeconfig: str | None = None,
        sudo: bool = True,
        ignore_not_found: bool = True,
    ) -> str | None:
        parts: list[str] = ["kubectl", "delete", "-f", manifest]
        if namespace:
            parts.extend(["--namespace", namespace])
        if kubeconfig:
            parts.extend(["--kubeconfig", kubeconfig])
        if ignore_not_found:
            parts.append("--ignore-not-found")
        command = _quote_command(parts)
        result = self._run_task(
            connection,
            group=TaskGroup.KUBERNETES,
            command=command,
            sudo=sudo,
        )
        return result

    def k8s_delete_resource(
        self,
        connection: Connection,
        resource_type: str,
        name: str,
        *,
        namespace: str | None = None,
        kubeconfig: str | None = None,
        sudo: bool = True,
        ignore_not_found: bool = True,
        extra_args: Sequence[str] | None = None,
    ) -> str | None:
        parts: list[str] = ["kubectl", "delete", resource_type, name]
        if namespace:
            parts.extend(["--namespace", namespace])
        if kubeconfig:
            parts.extend(["--kubeconfig", kubeconfig])
        if ignore_not_found:
            parts.append("--ignore-not-found")
        if extra_args:
            parts.extend(extra_args)
        command = _quote_command(parts)
        result = self._run_task(
            connection,
            group=TaskGroup.KUBERNETES,
            command=command,
            sudo=sudo,
        )
        return result

    def docker_list_container(self, connection: Connection) -> list[list[str]]:
        res = (
            self._run_task(
                connection,
                group=TaskGroup.CONTAINER_RUNTIME,
                command="docker container ls",
                sudo=True,
            )
            or ""
        )
        dl = str(res).split("\n")
        dlist = [re.sub(r"\ {2,}", "    ", dl[i]).split("   ") for i in range(len(dl))]
        return dlist

    def docker_down(
        self,
        connection: Connection,
        config_yaml: str,
        remove_volumes: bool = False,
    ) -> str | None:
        volumes = "--volumes " if remove_volumes else ""
        command = f'docker compose -f "{config_yaml}" down {volumes}--remove-orphans'
        result = self._run_task(
            connection,
            group=TaskGroup.CONTAINER_RUNTIME,
            command=command,
            sudo=True,
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
        result = self._run_task(
            connection,
            group=TaskGroup.CONTAINER_RUNTIME,
            command=command,
            sudo=True,
        )
        return result

    def docker_service_state(self, connection: Connection, service_name: str) -> str:
        cmd = f"docker inspect --format '{{{{.State.Status}}}}' {service_name}"
        res = (
            self._run_task(
                connection,
                group=TaskGroup.CONTAINER_RUNTIME,
                command=cmd,
                sudo=True,
                pty=False,
            )
            or ""
        )
        return res

    def docker_all_service_states(
        self, connection: Connection
    ) -> dict[str, dict[Any, Any]]:
        ids = self._run_task(
            connection,
            group=TaskGroup.CONTAINER_RUNTIME,
            command="docker ps -aq",
            sudo=True,
            pty=False,
        )
        if not ids:
            return {}

        id_list = " ".join(ids.split())
        inspect_output = self._run_task(
            connection,
            group=TaskGroup.CONTAINER_RUNTIME,
            command=f"docker inspect {id_list}",
            sudo=True,
            pty=False,
        )
        try:
            containers = json.loads(inspect_output or "[]")
            result = {
                c.get("Name", "").lstrip("/"): c.get("State", {}) for c in containers
            }
            return result
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("Failed to parse docker state info: %s", exc)
            return {}

    def docker_service_log_tails(
        self, connection: Connection, service_name: str, tail: int = 200
    ) -> str:
        try:
            cmd = f"docker logs --tail {int(tail)} {service_name}"
            res = (
                self._run_task(
                    connection,
                    group=TaskGroup.CONTAINER_RUNTIME,
                    command=cmd,
                    sudo=True,
                    pty=False,
                )
                or "No docker logs found"
            )
            return res
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("Failed to fetch logs for %s: %s", service_name, exc)
            return "Failed to fetch logs"

    def git_clone(
        self, connection: Connection, repo_url: str, install_path: str
    ) -> None:
        try:
            self._run_task(
                connection,
                group=TaskGroup.FILESYSTEM,
                command=f"mkdir -p {install_path}",
            )
            self._run_task(
                connection,
                group=TaskGroup.VERSION_CONTROL,
                command=f"cd {install_path}; git clone {repo_url}",
            )
        except Exception as exc:  # pragma: no cover - defensive
            raise

    def git_run(
        self,
        connection: Connection,
        git_args: Sequence[str],
        *,
        working_dir: str,
        env: Mapping[str, str] | None = None,
        sudo: bool = False,
        pty: bool = False,
    ) -> str | None:
        env_prefix = ""
        if env:
            env_prefix = " ".join(
                f"{key}={shlex.quote(value)}" for key, value in env.items()
            )
            if env_prefix:
                env_prefix += " "
        command = (
            f"cd {shlex.quote(working_dir)} && "
            f"{env_prefix}{_quote_command(['git', *git_args])}"
        )
        result = self._run_task(
            connection,
            group=TaskGroup.VERSION_CONTROL,
            command=command,
            sudo=sudo,
            pty=pty,
        )
        return result

    def fs_copy(self, connection: Connection, src_file: str, dst_path: str) -> None:
        try:
            connection.put(src_file, dst_path)
        except Exception as exc:  # pragma: no cover - defensive
            raise

    def fs_create_dir(self, connection: Connection, path: str) -> None:
        self._run_task(
            connection,
            group=TaskGroup.FILESYSTEM,
            command=f"mkdir -p {path}",
        )

    def fs_delete_dir(self, connection: Connection, path: str) -> None:
        self._run_task(
            connection,
            group=TaskGroup.FILESYSTEM,
            command=f"rm -rf {path}",
            sudo=True,
        )

    def fs_copy_dir(
        self,
        connection: Connection,
        src_path: str,
        dst_path: str,
        sudo: bool = False,
    ) -> None:
        self._run_task(
            connection,
            group=TaskGroup.FILESYSTEM,
            command=f"cp -r {src_path} {dst_path}",
            sudo=sudo,
        )

    def fs_copy_remote_file(
        self,
        connection: Connection,
        source: str,
        destination: str,
        *,
        sudo: bool = False,
    ) -> None:
        """Copy a file on the remote host."""

        self._run_task(
            connection,
            group=TaskGroup.FILESYSTEM,
            command=f"cp {source} {destination}",
            sudo=sudo,
        )

    def fs_concatenate_files(
        self,
        connection: Connection,
        sources: Sequence[str],
        destination: str,
        *,
        sudo: bool = False,
    ) -> None:
        if not sources:
            raise ValueError("At least one source file is required")
        sources_segment = " ".join(shlex.quote(src) for src in sources)
        command = f"cat {sources_segment} > {shlex.quote(destination)}"
        self._run_task(
            connection,
            group=TaskGroup.FILESYSTEM,
            command=command,
            sudo=sudo,
        )

    def fs_set_permissions(
        self,
        connection: Connection,
        path: str,
        mode: str,
        *,
        recursive: bool = False,
        sudo: bool = False,
    ) -> None:
        """Update permissions on the remote host."""

        recursive_flag = " -R" if recursive else ""
        self._run_task(
            connection,
            group=TaskGroup.FILESYSTEM,
            command=f"chmod{recursive_flag} {mode} {path}",
            sudo=sudo,
        )

    def fs_exists_dir(self, connection: Connection, path: str) -> bool:
        try:
            res = self._run_task(
                connection,
                group=TaskGroup.FILESYSTEM,
                command=f"test -d {path} && echo exists || echo missing",
            )
            exists = str(res).strip() == "exists"
            return exists
        except Exception as exc:  # pragma: no cover - defensive
            return False

    def fs_create_symlink(
        self,
        connection: Connection,
        target_path: str,
        link_path: str,
        sudo: bool = False,
    ) -> None:
        self._run_task(
            connection,
            group=TaskGroup.FILESYSTEM,
            command=f"ln -s {target_path} {link_path}",
            sudo=sudo,
        )

    def fs_remove_symlink(
        self, connection: Connection, link_path: str, sudo: bool = False
    ) -> None:
        self._run_task(
            connection,
            group=TaskGroup.FILESYSTEM,
            command=f"rm {link_path}",
            sudo=sudo,
        )

    def fs_touch(self, connection: Connection, fname: str) -> None:
        self._run_task(
            connection,
            group=TaskGroup.FILESYSTEM,
            command=f"touch {fname}",
        )

    def fs_append_line(self, connection: Connection, fname: str, line: str) -> None:
        self._run_task(
            connection,
            group=TaskGroup.FILESYSTEM,
            command=f"touch {fname}",
        )
        self._run_task(
            connection,
            group=TaskGroup.FILESYSTEM,
            command=f"echo '{line}' >> {fname}",
        )

    def fs_create_empty_file(self, connection: Connection, fname: str) -> None:
        self._run_task(
            connection,
            group=TaskGroup.FILESYSTEM,
            command=f"echo -n >| {fname}",
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
        self._run_task(
            connection,
            group=TaskGroup.FILESYSTEM,
            command=(
                f"sed -i 's{separator}{old}{separator}{new}{separator}g' {fname}"
            ),
            sudo=sudo,
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
                self._run_task(
                    connection,
                    group=TaskGroup.FILESYSTEM,
                    command=f"mv {remote_tmp_path} {file_path}",
                    sudo=True,
                )
                logger.info(
                    "Moved temporary file from %s to %s using sudo.",
                    remote_tmp_path,
                    file_path,
                )
            except Exception as exc:  # pragma: no cover - defensive
                logger.error("Error writing file %s with sudo: %s", file_path, exc)
                if connection.is_connected:
                    self._run_task(
                        connection,
                        group=TaskGroup.FILESYSTEM,
                        command=f"rm -f {remote_tmp_path}",
                        sudo=True,
                        pty=False,
                    )
                raise


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
        return data

    def fs_list_files(
        self, connection: Connection, path: str, sudo: bool = False
    ) -> list[str]:
        command = f"ls -A1 {path}"
        output = (
            self._run_task(
                connection,
                group=TaskGroup.FILESYSTEM,
                command=command,
                sudo=sudo,
                pty=False,
            )
            or ""
        )
        entries = output.splitlines() if output else []
        return entries

    def fs_list_file_tree(
        self, connection: Connection, path: str, sudo: bool = False
    ) -> list[dict[str, Any]]:
        command = f"find {path} -printf '%p|%y|%s|%TY-%Tm-%Td %TH:%TM:%TS\\n'"
        output = (
            self._run_task(
                connection,
                group=TaskGroup.FILESYSTEM,
                command=command,
                sudo=sudo,
                pty=False,
            )
            or ""
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

        return entries
