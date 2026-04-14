"""Filesystem helpers for Ubuntu executors."""

from __future__ import annotations

import logging
import os
import secrets
import shlex
from io import BytesIO
from typing import Any, Sequence

import yaml
from fabric import Connection  # type: ignore

from mlox.execution.base import TaskGroup, TaskRunnerABC

logger = logging.getLogger(__name__)


class FilesystemMixin(TaskRunnerABC):
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
        """Create an empty file, truncating if it exists. Attention: echo -n >| will not work on e.g. OSX"""
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
            command=(f"sed -i 's{separator}{old}{separator}{new}{separator}g' {fname}"),
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
