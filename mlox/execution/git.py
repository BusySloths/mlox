"""Git command helpers for Ubuntu executors."""

from __future__ import annotations

import shlex
from typing import Mapping, Sequence

from fabric import Connection  # type: ignore

from mlox.execution.base import TaskGroup, TaskRunnerABC, _quote_command


class GitMixin(TaskRunnerABC):
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
