#!/usr/bin/env python3
"""Copy a legacy encrypted .project and its secret-manager data into a .mlox file.

The source file is opened read-only at the application level and its SHA-256 digest is
verified after import. The destination is removed if any step fails.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from cryptography.fernet import Fernet

from mlox.infra import Infrastructure
from mlox.project.store import ProjectDatabase, resolve_project_path
from mlox.utils import _get_encryption_key

INFRASTRUCTURE_SECRET = "MLOX_CONFIG_INFRASTRUCTURE"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _legacy_manager(project: dict[str, Any]):
    qualified = project.get("secret_manager_class")
    if not qualified:
        return None
    module_name, class_name = qualified.rsplit(".", 1)
    module = __import__(module_name, fromlist=[class_name])
    return getattr(module, class_name).instantiate_secret_manager(
        project.get("secret_manager_info", {})
    )


def migrate_legacy_project(
    source: str | Path,
    destination: str | Path,
    legacy_password: str,
    new_password: str,
    *,
    include_secrets: bool = True,
) -> Path:
    source_path = Path(source).expanduser().resolve()
    before = _sha256(source_path)
    encrypted = source_path.read_bytes()
    cleartext = Fernet(_get_encryption_key(legacy_password)).decrypt(encrypted)
    project = json.loads(cleartext.decode("utf-8"))
    if not isinstance(project, dict):
        raise ValueError("Legacy project metadata is invalid.")

    store = ProjectDatabase.create(
        destination, new_password, project.get("name") or source_path.stem
    )
    try:
        manager = _legacy_manager(project)
        secret_values: dict[str, Any] = {}
        if manager:
            secret_values = manager.list_secrets(keys_only=False)
        infra_payload = secret_values.pop(INFRASTRUCTURE_SECRET, None)
        if infra_payload is None and manager:
            infra_payload = manager.load_secret(INFRASTRUCTURE_SECRET)
        infra = (
            Infrastructure()
            if not infra_payload
            else Infrastructure.from_dict(infra_payload)
        )
        destination_project = store.load()
        destination_project.name = project.get("name") or source_path.stem
        destination_project.descr = project.get("descr", "")
        destination_project.version = project.get("version", "0.1.0")
        destination_project.created_at = (
            project.get("created_at") or destination_project.created_at
        )
        destination_project.infrastructure = infra
        store.save(destination_project)
        if include_secrets:
            for name, value in secret_values.items():
                store.save_secret(name, value)
        resource_count = len(infra.bundles) + sum(
            len(bundle.services) for bundle in infra.bundles
        )
        store.record_legacy_import(
            str(source_path), before, resource_count, len(secret_values) if include_secrets else 0
        )
        if not store.integrity_check():
            raise RuntimeError("Destination integrity check failed.")
        if before != _sha256(source_path):
            raise RuntimeError("Legacy source changed during migration.")
    except Exception:
        store.discard()
        raise
    return resolve_project_path(destination)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", help="Legacy encrypted .project file")
    parser.add_argument("destination", help="New encrypted .mlox file")
    parser.add_argument("--legacy-password", required=True)
    parser.add_argument("--new-password", required=True)
    parser.add_argument("--skip-secrets", action="store_true")
    args = parser.parse_args()
    output = migrate_legacy_project(
        args.source, args.destination, args.legacy_password, args.new_password,
        include_secrets=not args.skip_secrets,
    )
    print(f"Created {output}; legacy source was not modified.")


if __name__ == "__main__":
    main()
