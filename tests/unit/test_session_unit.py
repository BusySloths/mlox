from __future__ import annotations

import pytest

from mlox.project.store import ProjectAlreadyExistsError, ProjectNotFoundError
from mlox.secret_manager import InMemorySecretManager
from mlox.session import MloxSession, load_mlox_session


def test_session_creation_is_explicit_and_round_trips(tmp_path):
    path = tmp_path / "demo"
    session = MloxSession.create(str(path), "pw")
    session.secrets.save_secret("TOKEN", {"value": "secret"})
    session.save_infrastructure()

    reopened = MloxSession(str(path), "pw")

    assert reopened.project.name == "demo"
    assert reopened.project.data_source_kind == "sqlcipher"
    assert reopened.project.data_source_location == "self"
    assert reopened.secrets.load_secret("TOKEN") == {"value": "secret"}
    assert reopened.infra.bundles == []


def test_open_missing_project_does_not_implicitly_create(tmp_path):
    with pytest.raises(ProjectNotFoundError):
        MloxSession(str(tmp_path / "missing"), "pw")


def test_create_refuses_to_overwrite(tmp_path):
    path = tmp_path / "demo"
    MloxSession.create(str(path), "pw")
    with pytest.raises(ProjectAlreadyExistsError):
        MloxSession.create(str(path), "pw")


def test_check_project_exists_and_loads(tmp_path):
    path = tmp_path / "demo"
    MloxSession.create(str(path), "right")
    assert MloxSession.check_project_exists_and_loads(str(path), "right")
    assert not MloxSession.check_project_exists_and_loads(str(path), "wrong")


def test_external_secret_manager_is_imported_not_activated(tmp_path):
    session = MloxSession.create(str(tmp_path / "demo"), "pw")
    external = InMemorySecretManager()
    external.save_secret("TOKEN", "value")
    external.save_secret("MLOX_CONFIG_INFRASTRUCTURE", {"legacy": True})

    session.set_secret_manager(external)

    assert session.secrets.load_secret("TOKEN") == "value"
    assert session.secrets.load_secret("MLOX_CONFIG_INFRASTRUCTURE") is None
    assert session.project.data_source_kind == "sqlcipher"


def test_load_mlox_session_prefers_project_path(tmp_path, monkeypatch):
    path = tmp_path / "demo.mlox"
    MloxSession.create(str(path), "pw")
    monkeypatch.setenv("MLOX_PROJECT_PATH", str(path))
    monkeypatch.setenv("MLOX_PROJECT_PASSWORD", "pw")

    loaded = load_mlox_session()

    assert loaded.project_path == path.resolve()
