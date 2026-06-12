from __future__ import annotations

import pytest
from unittest import mock

from mlox.project import (
    ProjectAlreadyExistsError,
    ProjectNotFoundError,
    ProjectWorkspace,
)
from mlox.project.repository import SqlCipherRepository
from mlox.project.secrets import SecretManagerUnavailableError
from mlox.secret_manager import get_encrypted_access_keyfile
from mlox.service import AbstractSecretManagerService
from tests.secret_manager_fakes import SerializableSecretManager


class _SecretManagerService(AbstractSecretManagerService):
    def __init__(self, service_uuid, manager):
        self.uuid = service_uuid
        self.name = "external"
        self.target_path = "/external"
        self.state = "running"
        self._manager = manager

    def get_secret_manager(self, infra):
        return self._manager


class _Infrastructure:
    def __init__(self, service=None):
        self.service = service
        self.bundles = []

    def get_service_by_uuid(self, service_uuid):
        if self.service and self.service.uuid == service_uuid:
            return self.service
        return None

    def services(self):
        if self.service:
            yield self.service

    def get_service(self, name):
        if self.service and self.service.name == name:
            return self.service
        return None

    def filter_by_group(self, group):
        return [self.service] if group == "secret-manager" and self.service else []


def test_workspace_creation_commit_and_reload(tmp_path):
    path = tmp_path / "demo"
    workspace = ProjectWorkspace.create(str(path), "pw")
    workspace.descr = "changed"
    workspace.secrets.save_secret("TOKEN", {"value": "secret"})
    workspace.commit()

    reopened = ProjectWorkspace.open(str(path), "pw")

    assert reopened.name == "demo"
    assert reopened.descr == "changed"
    assert reopened.data_source_kind == "sqlcipher"
    assert reopened.data_source_location == "self"
    assert reopened.secrets.load_secret("TOKEN") == {"value": "secret"}
    assert reopened.infrastructure.bundles == []

    reopened.descr = "discarded"
    reopened.reload()
    assert reopened.descr == "changed"


def test_open_missing_project_does_not_implicitly_create(tmp_path):
    with pytest.raises(ProjectNotFoundError):
        ProjectWorkspace.open(str(tmp_path / "missing"), "pw")


def test_create_refuses_to_overwrite(tmp_path):
    path = tmp_path / "demo"
    ProjectWorkspace.create(str(path), "pw")
    with pytest.raises(ProjectAlreadyExistsError):
        ProjectWorkspace.create(str(path), "pw")


def test_can_open_project(tmp_path):
    path = tmp_path / "demo"
    ProjectWorkspace.create(str(path), "right")
    assert ProjectWorkspace.can_open(str(path), "right")
    assert not ProjectWorkspace.can_open(str(path), "wrong")


def test_external_secret_manager_is_imported_not_activated(tmp_path):
    workspace = ProjectWorkspace.create(str(tmp_path / "demo"), "pw")
    external = SerializableSecretManager()
    external.save_secret("TOKEN", "value")
    external.save_secret("MLOX_CONFIG_INFRASTRUCTURE", {"legacy": True})

    workspace.import_secrets(external)

    assert workspace.secrets.load_secret("TOKEN") == "value"
    assert workspace.secrets.load_secret("MLOX_CONFIG_INFRASTRUCTURE") is None


def test_switching_secret_manager_copies_secrets_before_updating_pointer(tmp_path):
    workspace = ProjectWorkspace.create(str(tmp_path / "demo"), "pw")
    workspace.secrets.save_secret("TOKEN", "value")
    target = SerializableSecretManager()
    service = _SecretManagerService("service-1", target)
    workspace._state.infrastructure = _Infrastructure(service)
    workspace.commit = mock.Mock()

    result = workspace.set_secret_manager(service.uuid)

    assert result.success
    assert target.load_secret("TOKEN") == "value"
    assert workspace.secrets is target
    assert workspace.secret_manager_kind == "service"
    assert workspace.secret_manager_service_uuid == service.uuid
    workspace.commit.assert_called_once_with()


def test_unavailable_selected_manager_does_not_fall_back_to_embedded(tmp_path):
    repository = SqlCipherRepository.create(tmp_path / "demo", "pw")
    state = repository.load()
    state.secret_manager_kind = "service"
    state.secret_manager_service_uuid = "missing-service"
    repository.save(state)

    workspace = ProjectWorkspace.open(str(tmp_path / "demo"), "pw")

    assert workspace.secret_manager_kind == "service"
    assert workspace.secret_manager_service_uuid == "missing-service"
    assert workspace.secret_manager_status == "unavailable"
    active = [item for item in workspace.list_secret_managers() if item.is_active]
    assert len(active) == 1
    assert active[0].service_uuid == "missing-service"
    assert not active[0].is_available
    with pytest.raises(SecretManagerUnavailableError):
        workspace.secrets.list_secrets()


def test_unavailable_manager_can_be_explicitly_reset_without_migration(tmp_path):
    repository = SqlCipherRepository.create(tmp_path / "demo", "pw")
    state = repository.load()
    state.secret_manager_kind = "service"
    state.secret_manager_service_uuid = "missing-service"
    repository.save(state)
    workspace = ProjectWorkspace.open(str(tmp_path / "demo"), "pw")

    result = workspace.use_embedded_secret_manager(migrate=False)

    assert result.success
    assert workspace.secret_manager_kind == "embedded"
    assert workspace.secret_manager_service_uuid is None
    assert workspace.secret_manager_status == "available"


def test_embedded_manager_is_listed_and_does_not_export_keyfiles(tmp_path):
    workspace = ProjectWorkspace.create(str(tmp_path / "demo"), "pw")

    descriptors = workspace.list_secret_managers()

    assert len(descriptors) == 1
    assert descriptors[0].name == "Embedded Project Storage"
    assert descriptors[0].is_active
    assert not descriptors[0].supports_keyfile_export
    with pytest.raises(ValueError, match="does not support keyfile export"):
        get_encrypted_access_keyfile(workspace.secrets, "pw")


def test_listing_secret_managers_does_not_poll_inactive_services(tmp_path):
    workspace = ProjectWorkspace.create(str(tmp_path / "demo"), "pw")
    manager = SerializableSecretManager()
    manager.is_working = mock.Mock(return_value=True)
    service = _SecretManagerService("service-1", manager)
    service.get_secret_manager = mock.Mock(return_value=manager)
    workspace._state.infrastructure = _Infrastructure(service)

    descriptor = next(
        item
        for item in workspace.list_secret_managers()
        if item.id == service.uuid
    )

    assert descriptor.is_available is None
    assert descriptor.manager is None
    service.get_secret_manager.assert_not_called()
    manager.is_working.assert_not_called()

    probed = workspace.probe_secret_manager(service.uuid)

    assert probed.is_available is True
    service.get_secret_manager.assert_called_once_with(
        workspace.infrastructure
    )
    manager.is_working.assert_called_once_with()


def test_active_secret_manager_service_cannot_be_removed(tmp_path):
    workspace = ProjectWorkspace.create(str(tmp_path / "demo"), "pw")
    service = _SecretManagerService("service-1", SerializableSecretManager())
    workspace._state.infrastructure = _Infrastructure(service)
    workspace._state.secret_manager_kind = "service"
    workspace._state.secret_manager_service_uuid = service.uuid

    result = workspace.teardown_service(name=service.name)

    assert not result.success
    assert "active secret manager" in result.message


def test_workspace_exposes_resolved_path(tmp_path):
    path = tmp_path / "demo"
    workspace = ProjectWorkspace.create(str(path), "pw")
    assert workspace.path == path.with_suffix(".mlox").resolve()
