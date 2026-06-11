from __future__ import annotations

import sqlite3

from mlox.infra import Infrastructure
from mlox.project.store import ProjectDatabase, resolve_project_path


def test_project_path_adds_suffix_and_uses_project_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("MLOX_PROJECT_DIR", str(tmp_path))
    assert resolve_project_path("demo") == (tmp_path / "demo.mlox").resolve()


def test_schema_contains_portable_resource_and_data_source_tables(tmp_path):
    store = ProjectDatabase.create(tmp_path / "demo", "pw")
    with store.connection() as conn:
        tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        source = conn.execute("SELECT kind, location FROM data_sources").fetchone()
    assert {"projects", "data_sources", "bundles", "servers", "services", "secrets"} <= tables
    assert source == ("sqlcipher", "self")


def test_infrastructure_and_secrets_round_trip(tmp_path):
    store = ProjectDatabase.create(tmp_path / "demo", "pw")
    store.save_infrastructure(Infrastructure())
    store.save_secret("API_KEY", {"token": "abc"})
    reopened = ProjectDatabase(tmp_path / "demo", "pw").open()
    assert reopened.load_infrastructure().bundles == []
    assert reopened.load_secret("API_KEY") == {"token": "abc"}
    assert reopened.list_secrets(keys_only=True) == {"API_KEY": None}
    assert reopened.integrity_check()


def test_project_database_is_not_plain_json(tmp_path):
    store = ProjectDatabase.create(tmp_path / "demo", "pw")
    assert not store.path.read_bytes().startswith(b"{")
    # In unit tests this is SQLite, but production rejects this driver unless explicitly enabled.
    with sqlite3.connect(store.path) as conn:
        assert conn.execute("SELECT schema_version FROM schema_info").fetchone() == (1,)
