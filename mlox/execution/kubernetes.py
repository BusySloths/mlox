"""Helm and Kubernetes command helpers for Ubuntu executors."""

from __future__ import annotations

import json
from typing import Any, Mapping, Sequence

from fabric import Connection  # type: ignore

from mlox.execution.base import TaskGroup, TaskRunnerABC, _quote_command


class KubernetesMixin(TaskRunnerABC):
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
        parts: list[str] = [
            "kubectl",
            "create",
            "token",
            service_account,
            "--namespace",
            namespace,
        ]
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

    def k8s_resource_log_tail(
        self,
        connection: Connection,
        resource: str,
        *,
        namespace: str,
        tail: int = 200,
        kubeconfig: str | None = None,
        container: str | None = None,
        sudo: bool = True,
    ) -> str:
        parts: list[str] = [
            "kubectl",
            "logs",
            resource,
            "--namespace",
            namespace,
            "--tail",
            str(int(tail)),
        ]
        if container:
            parts.extend(["--container", container])
        if kubeconfig:
            parts.extend(["--kubeconfig", kubeconfig])
        command = _quote_command(parts)
        result = self._run_task(
            connection,
            group=TaskGroup.KUBERNETES,
            command=command,
            sudo=sudo,
            pty=False,
            description=f"Fetch Kubernetes logs for {namespace}/{resource}",
            extra_metadata={
                "log_source": "kubernetes",
                "namespace": namespace,
                "resource": resource,
                "container": container or "",
                "tail": int(tail),
            },
        )
        return result or "No Kubernetes logs found"

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
