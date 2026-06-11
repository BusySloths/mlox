from __future__ import annotations

import pytest

from mlox.project.store import ProjectAlreadyExistsError, ProjectNotFoundError
from mlox.secret_manager import InMemorySecretManager
from mlox.session import ProjectSession, load_project_session


def test_project_session_creation_commit_and_reload(tmp_path):
    path = tmp_path / "demo"
    session = ProjectSession.create(str(path), "pw")
    session.project.descr = "changed"
    session.secrets.save_secret("TOKEN", {"value": "secret"})
    session.commit()

    reopened = ProjectSession.open(str(path), "pw")

    assert reopened.project.name == "demo"
    assert reopened.project.descr == "changed"
    assert reopened.project.data_source_kind == "sqlcipher"
    assert reopened.project.data_source_location == "self"
    assert reopened.secrets.load_secret("TOKEN") == {"value": "secret"}
    assert reopened.project.infrastructure.bundles == []

    reopened.project.descr = "discarded"
    reopened.reload()
    assert reopened.project.descr == "changed"


def test_open_missing_project_does_not_implicitly_create(tmp_path):
    with pytest.raises(ProjectNotFoundError):
        ProjectSession.open(str(tmp_path / "missing"), "pw")


def test_create_refuses_to_overwrite(tmp_path):
    path = tmp_path / "demo"
    ProjectSession.create(str(path), "pw")
    with pytest.raises(ProjectAlreadyExistsError):
        ProjectSession.create(str(path), "pw")


def test_can_open_project(tmp_path):
    path = tmp_path / "demo"
    ProjectSession.create(str(path), "right")
    assert ProjectSession.can_open(str(path), "right")
    assert not ProjectSession.can_open(str(path), "wrong")


def test_external_secret_manager_is_imported_not_activated(tmp_path):
    session = ProjectSession.create(str(tmp_path / "demo"), "pw")
    external = InMemorySecretManager()
    external.save_secret("TOKEN", "value")
    external.save_secret("MLOX_CONFIG_INFRASTRUCTURE", {"legacy": True})

    session.import_secrets(external)

    assert session.secrets.load_secret("TOKEN") == "value"
    assert session.secrets.load_secret("MLOX_CONFIG_INFRASTRUCTURE") is None


def test_load_project_session_prefers_project_path(tmp_path, monkeypatch):
    path = tmp_path / "demo.mlox"
    ProjectSession.create(str(path), "pw")
    monkeypatch.setenv("MLOX_PROJECT_PATH", str(path))
    monkeypatch.setenv("MLOX_PROJECT_PASSWORD", "pw")

    loaded = load_project_session()

    assert loaded.path == path.resolve()
