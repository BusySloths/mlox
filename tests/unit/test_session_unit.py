from __future__ import annotations

from dataclasses import dataclass

import pytest

from mlox.secret_manager import InMemorySecretManager
from mlox.session import MloxProject, MloxSession, load_mlox_session
from mlox.infra import Infrastructure


@dataclass
class _Migration:
    name: str = "m1"

    def _migrate_childs(self, data):
        data["migrated"] = True
        return data


class _BrokenSecret:
    @classmethod
    def instantiate_secret_manager(cls, info):
        return None


@pytest.fixture
def minimal_session(monkeypatch):
    monkeypatch.setattr(MloxSession, "load_project", lambda self, name: setattr(self, "project", MloxProject(name=name)))
    monkeypatch.setattr(MloxSession, "save_project", lambda self: None)
    return MloxSession("proj", "pw")


def test_check_project_exists_and_loads_true(monkeypatch):
    monkeypatch.setattr("mlox.session.load_from_json", lambda path, password, encrypted=True: {"ok": True})
    assert MloxSession.check_project_exists_and_loads("proj", "pw") is True


def test_check_project_exists_and_loads_false(monkeypatch):
    def _raise(*_args, **_kwargs):
        raise ValueError("bad")

    monkeypatch.setattr("mlox.session.load_from_json", _raise)
    assert MloxSession.check_project_exists_and_loads("proj", "pw") is False


def test_set_secret_manager_updates_project(minimal_session):
    sm = InMemorySecretManager()

    minimal_session.set_secret_manager(sm)

    assert minimal_session.secrets is sm
    assert minimal_session.project.secret_manager_class.endswith("InMemorySecretManager")


def test_set_secret_manager_none_clears_project(minimal_session):
    minimal_session.project.secret_manager_info = {"x": 1}

    minimal_session.set_secret_manager(None)

    assert minimal_session.project.secret_manager_class is None
    assert minimal_session.project.secret_manager_info == {}


def test_load_secret_manager_import_failure(minimal_session, monkeypatch):
    minimal_session.project.secret_manager_class = "nope.module.Class"

    minimal_session.load_secret_manager()

    assert minimal_session.secrets is None


def test_load_secret_manager_instantiation_failure(minimal_session, monkeypatch):
    minimal_session.project.secret_manager_class = "tests.unit.test_session_unit._BrokenSecret"
    minimal_session.project.secret_manager_info = {}

    minimal_session.load_secret_manager()

    assert minimal_session.secrets is None


def test_save_infrastructure_no_secret_manager(minimal_session, caplog):
    minimal_session.secrets = None

    minimal_session.save_infrastructure()

    assert "Skipping infrastructure persistence" in caplog.text


def test_load_infrastructure_without_secrets_sets_blank(minimal_session):
    minimal_session.secrets = None

    minimal_session.load_infrastructure()

    assert minimal_session.infra.to_dict().get("bundles") == []


def test_load_infrastructure_with_invalid_type_raises(minimal_session):
    sm = InMemorySecretManager()
    sm.save_secret("MLOX_CONFIG_INFRASTRUCTURE", "not-a-dict")
    minimal_session.secrets = sm

    with pytest.raises(ValueError, match="expected format"):
        minimal_session.load_infrastructure()


def test_load_infrastructure_applies_migrations(monkeypatch):
    monkeypatch.setattr(MloxSession, "load_project", lambda self, name: setattr(self, "project", MloxProject(name=name)))
    monkeypatch.setattr(MloxSession, "save_project", lambda self: None)
    monkeypatch.setattr(MloxSession, "load_secret_manager", lambda self: None)
    monkeypatch.setattr(MloxSession, "set_secret_manager", lambda self, sm: setattr(self, "secrets", sm))
    session = MloxSession("proj", "pw", migrations=[_Migration()])

    sm = InMemorySecretManager()
    payload = Infrastructure().to_dict()
    payload["v"] = 1
    sm.save_secret("MLOX_CONFIG_INFRASTRUCTURE", payload)
    session.secrets = sm

    session.load_infrastructure()

    assert session.infra.to_dict().get("bundles") == []


def test_load_mlox_session_requires_env(monkeypatch, capsys):
    monkeypatch.delenv("MLOX_PROJECT_NAME", raising=False)
    monkeypatch.delenv("MLOX_PROJECT_PASSWORD", raising=False)

    with pytest.raises(SystemExit):
        load_mlox_session()

    out = capsys.readouterr().out
    assert "environment variable is not set" in out


def test_load_mlox_session_happy_path(monkeypatch):
    monkeypatch.setenv("MLOX_PROJECT_NAME", "p")
    monkeypatch.setenv("MLOX_PROJECT_PASSWORD", "s")

    class _Session:
        def __init__(self, project_name, password, migrations=None):
            self.project_name = project_name
            self.password = password

    monkeypatch.setattr("mlox.session.MloxSession", _Session)

    s = load_mlox_session()

    assert s.project_name == "p"
    assert s.password == "s"
