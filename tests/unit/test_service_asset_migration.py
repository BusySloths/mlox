from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from mlox.infra import Bundle
from mlox.project import ProjectWorkspace
from scripts.migrate_project_asset_paths import (
    _portable_reference,
    apply_service_asset_migration,
    migrate_project_asset_paths,
    plan_service_asset_migration,
)
from mlox.servers.ubuntu.native import UbuntuNativeServer
from mlox.services.airflow.docker import AirflowDockerService


def _workspace_with_service(service):
    infrastructure = SimpleNamespace(services=lambda: iter([service]))
    return SimpleNamespace(infrastructure=infrastructure)


@pytest.mark.parametrize(
    "legacy_path",
    [
        "/Users/alice/Projects/mlox/mlox/services/airflow/"
        "docker-compose-airflow-3.1.3.yaml",
        "/opt/venv/lib/python3.12/site-packages/mlox/services/airflow/"
        "docker-compose-airflow-3.1.3.yaml",
        r"C:\Users\alice\mlox\mlox\services\airflow\docker-compose-airflow-3.1.3.yaml",
    ],
)
def test_migration_plans_portable_reference_for_legacy_platform_paths(legacy_path):
    service = SimpleNamespace(name="Airflow", uuid="airflow-1", template=legacy_path)
    workspace = _workspace_with_service(service)

    plan = plan_service_asset_migration(workspace)

    assert not plan.problems
    assert len(plan.changes) == 1
    assert plan.changes[0].new_value == (
        "airflow/docker-compose-airflow-3.1.3.yaml"
    )
    apply_service_asset_migration(workspace, plan)
    assert service.template == "airflow/docker-compose-airflow-3.1.3.yaml"


def test_migration_reports_unknown_absolute_asset_without_changing_it():
    service = SimpleNamespace(
        name="Custom", uuid="custom-1", template="/srv/custom/compose.yaml"
    )

    plan = plan_service_asset_migration(_workspace_with_service(service))

    assert not plan.changes
    assert len(plan.problems) == 1
    assert service.template == "/srv/custom/compose.yaml"


@pytest.mark.parametrize(
    ("legacy_reference", "expected"),
    [
        ("kubeapps/kubeapps.yaml", "kubeapps/mlox.kubeapps.yaml"),
        ("kubeflow/kubeflow.yaml", "kubeflow/mlox.kubeflow.yaml"),
        ("tsm/mlox.github.yaml", "github/mlox.github.yaml"),
    ],
)
def test_migration_maps_historical_missing_asset_aliases(legacy_reference, expected):
    legacy_path = f"/opt/mlox/mlox/services/{legacy_reference}"

    assert _portable_reference(legacy_path) == expected


@pytest.mark.parametrize(
    ("field_name", "legacy_reference"),
    [
        ("template", "redis/docker-compose-redis-8-bookworm.yaml"),
        ("template", "tsm/mlox.tsm.yaml"),
        ("template", "minio/docker-compose-minio.yaml"),
        ("template", "kafka/docker-compose-kafka-3.7.0.yaml"),
        ("template", "postgres/docker-compose-postgres-16.yaml"),
        ("template", "feast/docker-compose-feast.yaml"),
        ("dockerfile", "feast/Dockerfile"),
    ],
)
def test_migration_maps_legacy_stacks_root(field_name, legacy_reference):
    legacy_path = f"/Users/alice/Projects/mlox/mlox/stacks/{legacy_reference}"
    service = SimpleNamespace(name="Legacy", uuid="legacy-1")
    setattr(service, field_name, legacy_path)

    plan = plan_service_asset_migration(_workspace_with_service(service))

    assert not plan.problems
    assert len(plan.changes) == 1
    assert plan.changes[0].field == field_name
    assert plan.changes[0].new_value == legacy_reference


def test_migration_script_backs_up_and_verifies_encrypted_project(tmp_path):
    project_path = tmp_path / "portable.mlox"
    backup_path = tmp_path / "portable.before-assets.mlox"
    workspace = ProjectWorkspace.create(str(project_path), "pw")
    server = UbuntuNativeServer(
        ip="10.0.0.10",
        root="root",
        root_pw="pw",
        service_config_id="ubuntu-native",
    )
    bundle = Bundle("test", server)
    service = AirflowDockerService(
        name="Airflow",
        service_config_id="airflow-3.1.3-docker",
        template=(
            "/Users/alice/Projects/mlox/mlox/services/airflow/"
            "docker-compose-airflow-3.1.3.yaml"
        ),
        target_path="/home/mlox/airflow",
        path_dags="/home/mlox/airflow/dags",
        path_output="/home/mlox/airflow/output",
        ui_user="admin",
        ui_pw="pw",
        port="8080",
    )
    bundle.services.append(service)
    workspace.infrastructure.bundles.append(bundle)
    workspace.commit()

    changed = migrate_project_asset_paths(
        project_path,
        "pw",
        backup=backup_path,
    )

    assert changed == 1
    assert backup_path.is_file()
    reopened = ProjectWorkspace.open(str(project_path), "pw")
    migrated = next(reopened.infrastructure.services())
    assert migrated.template == "airflow/docker-compose-airflow-3.1.3.yaml"
    original = ProjectWorkspace.open(str(backup_path), "pw")
    assert Path(next(original.infrastructure.services()).template).is_absolute()
