#!/usr/bin/env python3
"""One-time migration for projects affected by MLOX issue #97.

Issue: https://github.com/BusySloths/mlox/issues/97

Older projects may contain absolute paths to built-in service assets from either
the historical ``mlox/stacks`` layout or the current ``mlox/services`` layout.
Those paths bind the encrypted project to the machine where a service was added.
This script replaces recognized absolute paths with portable references relative
to the installed ``mlox.services`` package.

Current MLOX code assumes all persisted built-in asset references are already
relative. Legacy recognition and conversion intentionally live only in this
script.

Preview a project without writing:

    uv run scripts/migrate_project_asset_paths.py PROJECT.mlox --dry-run

Apply the migration with a required, non-existing backup path:

    uv run scripts/migrate_project_asset_paths.py PROJECT.mlox \\
        --backup PROJECT.before-assets.mlox

The password is read from ``--password``, ``MLOX_PROJECT_PASSWORD``, or an
interactive prompt. Prefer the prompt so the password is not stored in shell
history. Unknown custom paths or missing packaged assets block all writes. After
committing, the script reopens and verifies the encrypted project; if that fails,
it restores the original project from the backup.
"""

from __future__ import annotations

import argparse
import getpass
import os
import shutil
from dataclasses import dataclass
from pathlib import Path
from pathlib import PureWindowsPath

from mlox.project import ProjectWorkspace, resolve_project_path
from mlox.service import service_asset_path


SERVICE_ASSET_FIELDS = (
    "template",
    "dockerfile",
    "start_script",
    "config",
    "serve_script",
    "ollama_script",
    "litellm_config",
)

LEGACY_SERVICE_ASSET_ALIASES = {
    "kubeapps/kubeapps.yaml": "kubeapps/mlox.kubeapps.yaml",
    "kubeflow/kubeflow.yaml": "kubeflow/mlox.kubeflow.yaml",
    "tsm/mlox.github.yaml": "github/mlox.github.yaml",
}


@dataclass(frozen=True)
class ServiceAssetChange:
    service_name: str
    service_uuid: str
    field: str
    old_value: str
    new_value: str


@dataclass(frozen=True)
class ServiceAssetProblem:
    service_name: str
    service_uuid: str
    field: str
    value: str
    message: str


@dataclass(frozen=True)
class ServiceAssetMigrationPlan:
    changes: tuple[ServiceAssetChange, ...]
    problems: tuple[ServiceAssetProblem, ...]


def _is_absolute(reference: str) -> bool:
    return Path(reference).is_absolute() or PureWindowsPath(reference).is_absolute()


def _portable_reference(reference: str) -> str | None:
    normalized = str(reference).replace("\\", "/")
    for asset_root in ("services", "stacks"):
        marker = f"/mlox/{asset_root}/"
        if marker in normalized:
            relative = normalized.rsplit(marker, 1)[1]
            return LEGACY_SERVICE_ASSET_ALIASES.get(relative, relative)
        prefix = f"mlox/{asset_root}/"
        if normalized.startswith(prefix):
            relative = normalized[len(prefix):]
            return LEGACY_SERVICE_ASSET_ALIASES.get(relative, relative)
    return None


def plan_service_asset_migration(workspace) -> ServiceAssetMigrationPlan:
    """Build and validate a non-mutating migration plan for one workspace."""

    changes: list[ServiceAssetChange] = []
    problems: list[ServiceAssetProblem] = []
    for service in workspace.infrastructure.services():
        service_name = str(getattr(service, "name", ""))
        service_uuid = str(getattr(service, "uuid", ""))
        for field_name in SERVICE_ASSET_FIELDS:
            value = getattr(service, field_name, None)
            if not isinstance(value, str) or not value:
                continue
            if not _is_absolute(value):
                try:
                    service_asset_path(value)
                except (FileNotFoundError, ValueError) as exc:
                    problems.append(
                        ServiceAssetProblem(
                            service_name,
                            service_uuid,
                            field_name,
                            value,
                            str(exc),
                        )
                    )
                continue
            reference = _portable_reference(value)
            if reference is None:
                problems.append(
                    ServiceAssetProblem(
                        service_name,
                        service_uuid,
                        field_name,
                        value,
                        "Absolute path is not a recognized built-in mlox service asset.",
                    )
                )
                continue
            try:
                service_asset_path(reference)
            except (FileNotFoundError, ValueError) as exc:
                problems.append(
                    ServiceAssetProblem(
                        service_name,
                        service_uuid,
                        field_name,
                        value,
                        str(exc),
                    )
                )
                continue
            changes.append(
                ServiceAssetChange(
                    service_name,
                    service_uuid,
                    field_name,
                    value,
                    reference,
                )
            )
    return ServiceAssetMigrationPlan(tuple(changes), tuple(problems))


def apply_service_asset_migration(workspace, plan: ServiceAssetMigrationPlan) -> None:
    """Apply a previously validated migration plan in memory."""

    if plan.problems:
        raise ValueError("Cannot migrate while unresolved service asset paths remain.")
    services = {
        str(getattr(service, "uuid", "")): service
        for service in workspace.infrastructure.services()
    }
    for change in plan.changes:
        service = services.get(change.service_uuid)
        if service is None:
            raise ValueError(f"Service disappeared during migration: {change.service_uuid}")
        if getattr(service, change.field, None) != change.old_value:
            raise ValueError(
                f"Service asset changed during migration: {change.service_name}."
                f"{change.field}"
            )
        setattr(service, change.field, change.new_value)


def _print_plan(plan) -> None:
    for change in plan.changes:
        print(
            f"CHANGE {change.service_name} ({change.service_uuid}) "
            f"{change.field}: {change.old_value} -> {change.new_value}"
        )
    for problem in plan.problems:
        print(
            f"BLOCKED {problem.service_name} ({problem.service_uuid}) "
            f"{problem.field}: {problem.value} ({problem.message})"
        )
    print(f"{len(plan.changes)} change(s), {len(plan.problems)} problem(s)")


def migrate_project_asset_paths(
    project: str | Path,
    password: str,
    *,
    backup: str | Path | None = None,
    dry_run: bool = False,
) -> int:
    """Migrate one encrypted project, restoring its backup on verification failure."""

    project_path = resolve_project_path(project)
    workspace = ProjectWorkspace.open(str(project_path), password)
    plan = plan_service_asset_migration(workspace)
    _print_plan(plan)
    if plan.problems:
        raise ValueError("Migration blocked by unrecognized or missing service assets.")
    if dry_run or not plan.changes:
        return len(plan.changes)
    if backup is None:
        raise ValueError("A backup path is required unless --dry-run is used.")

    backup_path = Path(backup).expanduser().resolve()
    if backup_path.exists():
        raise FileExistsError(f"Backup already exists: {backup_path}")
    backup_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(project_path, backup_path)
    try:
        apply_service_asset_migration(workspace, plan)
        workspace.commit()
        verified = ProjectWorkspace.open(str(project_path), password)
        verification = plan_service_asset_migration(verified)
        if verification.changes or verification.problems:
            raise RuntimeError("Migrated project did not pass asset-path verification.")
    except Exception:
        shutil.copy2(backup_path, project_path)
        raise
    return len(plan.changes)


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("project", help="Encrypted .mlox project file")
    parser.add_argument("--password", help="Project password (defaults to env or prompt)")
    parser.add_argument("--backup", help="Required non-existing backup path for mutation")
    parser.add_argument("--dry-run", action="store_true", help="Report without writing")
    args = parser.parse_args()
    password = (
        args.password
        or os.environ.get("MLOX_PROJECT_PASSWORD")
        or getpass.getpass("Project password: ")
    )
    changed = migrate_project_asset_paths(
        args.project,
        password,
        backup=args.backup,
        dry_run=args.dry_run,
    )
    action = "Would migrate" if args.dry_run else "Migrated"
    print(f"{action} {changed} service asset path(s).")


if __name__ == "__main__":
    main()
