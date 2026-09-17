"""Migration support for machine-specific service asset paths."""

from __future__ import annotations

from dataclasses import dataclass

from mlox.service import (
    SERVICE_ASSET_FIELDS,
    is_absolute_service_asset_reference,
    portable_service_asset_reference,
    service_asset_path,
)


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
            if not is_absolute_service_asset_reference(value):
                try:
                    with service_asset_path(value):
                        pass
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
            reference = portable_service_asset_reference(value)
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
                with service_asset_path(reference):
                    pass
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
