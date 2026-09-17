#!/usr/bin/env python3
"""Convert persisted local service asset paths to portable package references."""

from __future__ import annotations

import argparse
import getpass
import os
import shutil
from pathlib import Path

from mlox.project import ProjectWorkspace, resolve_project_path
from mlox.project.asset_migration import (
    apply_service_asset_migration,
    plan_service_asset_migration,
)


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
    parser = argparse.ArgumentParser(description=__doc__)
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
