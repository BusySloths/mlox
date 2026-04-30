from __future__ import annotations

from dataclasses import dataclass

from mlox.migrations.add_field_model_server_registry_uuid import (
    AddFieldModelServerRegistryUUID,
)
from mlox.migrations.base import MloxMigrations


@dataclass
class _AppendMarkerMigration(MloxMigrations):
    name: str
    marker: str

    def migrate(self, data: dict) -> dict:
        data.setdefault("order", []).append(self.marker)
        return self._migrate_childs(data)


class _AddFieldMigration(MloxMigrations):
    name = "add_field_test"

    def migrate(self, data: dict) -> dict:
        return self._add_field_to_class(
            data,
            module_name="target.module",
            class_name="TargetClass",
            field_name="registry_uuid",
            default_value=None,
        )


def test_add_field_to_class_updates_all_matching_objects_without_touching_existing_values():
    migration = _AddFieldMigration()
    payload = {
        "_module_name_": "root.module",
        "_class_name_": "RootClass",
        "items": [
            {
                "_module_name_": "target.module",
                "_class_name_": "TargetClass",
                "name": "first",
            },
            {
                "_module_name_": "target.module",
                "_class_name_": "TargetClass",
                "name": "second",
                "registry_uuid": "already-set",
            },
            {
                "_module_name_": "other.module",
                "_class_name_": "TargetClass",
                "name": "ignored-module",
            },
            {
                "_module_name_": "target.module",
                "_class_name_": "OtherClass",
                "name": "ignored-class",
            },
        ],
        "nested": {
            "service": {
                "_module_name_": "target.module",
                "_class_name_": "TargetClass",
                "name": "nested",
            }
        },
    }

    result = migration.migrate(payload)

    assert result["items"][0]["registry_uuid"] is None
    assert result["items"][1]["registry_uuid"] == "already-set"
    assert "registry_uuid" not in result["items"][2]
    assert "registry_uuid" not in result["items"][3]
    assert result["nested"]["service"]["registry_uuid"] is None


def test_migrate_childs_applies_children_in_declared_order():
    child_one = _AppendMarkerMigration(name="child-one", marker="child-one")
    child_two = _AppendMarkerMigration(name="child-two", marker="child-two")
    parent = _AppendMarkerMigration(
        name="parent",
        marker="parent",
    )
    parent.childs = [child_one, child_two]

    result = parent.migrate({})

    assert result["order"] == ["parent", "child-one", "child-two"]


def test_migrate_childs_returns_original_payload_when_no_children():
    parent = _AppendMarkerMigration(name="solo", marker="solo")

    result = parent.migrate({})

    assert result["order"] == ["solo"]


def test_add_field_model_server_registry_uuid_adds_missing_field_to_matching_services():
    migration = AddFieldModelServerRegistryUUID()
    payload = {
        "bundles": [
            {
                "services": [
                    {
                        "_module_name_": "mlox.services.mlflow_mlserver.docker",
                        "_class_name_": "MLFlowMLServerDockerService",
                        "name": "mlserver-a",
                    },
                    {
                        "_module_name_": "mlox.services.mlflow_mlserver.docker",
                        "_class_name_": "MLFlowMLServerDockerService",
                        "name": "mlserver-b",
                        "registry_uuid": "registry-1",
                    },
                    {
                        "_module_name_": "mlox.services.mlflow.docker",
                        "_class_name_": "MLFlowDockerService",
                        "name": "plain-mlflow",
                    },
                ]
            }
        ]
    }

    result = migration.migrate(payload)

    services = result["bundles"][0]["services"]
    assert services[0]["registry_uuid"] is None
    assert services[1]["registry_uuid"] == "registry-1"
    assert "registry_uuid" not in services[2]


def test_add_field_model_server_registry_uuid_runs_child_migrations_after_field_injection():
    child = _AppendMarkerMigration(name="child", marker="child")
    migration = AddFieldModelServerRegistryUUID()
    migration.childs = [child]
    payload = {
        "bundles": [
            {
                "services": [
                    {
                        "_module_name_": "mlox.services.mlflow_mlserver.docker",
                        "_class_name_": "MLFlowMLServerDockerService",
                        "name": "mlserver",
                    }
                ]
            }
        ]
    }

    result = migration.migrate(payload)

    assert result["bundles"][0]["services"][0]["registry_uuid"] is None
    assert result["order"] == ["child"]
