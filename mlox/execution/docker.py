"""Docker command helpers for Ubuntu executors."""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from fabric import Connection  # type: ignore

from mlox.execution.base import TaskGroup, TaskRunnerABC

logger = logging.getLogger(__name__)


class DockerMixin(TaskRunnerABC):
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
        env_file: str | None = None,
        remove_volumes: bool = False,
    ) -> str | None:
        parts: list[str] = ["docker compose"]
        if env_file is not None:
            parts.append(f"--env-file {env_file}")
        parts.append(f'-f "{config_yaml}"')
        parts.append("down")
        if remove_volumes:
            parts.append("--volumes")
        parts.append("--remove-orphans")
        command = " ".join(parts)
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
