from __future__ import annotations

import sqlite3

import pytest

from mlox.infra import Infrastructure
from mlox.project.repository import SqlCipherRepository, resolve_project_path


def test_project_path_adds_suffix_and_uses_project_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("MLOX_PROJECT_DIR", str(tmp_path))
    assert resolve_project_path("demo") == (tmp_path / "demo.mlox").resolve()


def test_schema_contains_portable_resource_and_data_source_tables(tmp_path):
    store = SqlCipherRepository.create(tmp_path / "demo", "pw")
    with store.connection() as conn:
        tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        source = conn.execute("SELECT kind, location FROM data_sources").fetchone()
    assert {"projects", "data_sources", "bundles", "servers", "services", "secrets"} <= tables
    assert source == ("sqlcipher", "self")


def test_infrastructure_and_secrets_round_trip(tmp_path):
    store = SqlCipherRepository.create(tmp_path / "demo", "pw")
    project = store.load()
    project.infrastructure = Infrastructure()
    store.save(project)
    store.save_secret("API_KEY", {"token": "abc"})
    reopened = SqlCipherRepository(tmp_path / "demo", "pw").open()
    assert reopened.load().infrastructure.bundles == []
    assert reopened.load_secret("API_KEY") == {"token": "abc"}
    assert reopened.list_secrets(keys_only=True) == {"API_KEY": None}
    assert reopened.integrity_check()


def test_project_metadata_and_infrastructure_commit_atomically(tmp_path, monkeypatch):
    store = SqlCipherRepository.create(tmp_path / "demo", "pw")
    project = store.load()
    project.name = "changed"

    def fail_infrastructure_save(*args, **kwargs):
        raise RuntimeError("infrastructure write failed")

    monkeypatch.setattr(store, "_save_infrastructure", fail_infrastructure_save)

    with pytest.raises(RuntimeError, match="infrastructure write failed"):
        store.save(project)

    assert store.load().name == "demo"


def test_project_repository_is_not_plain_json(tmp_path):
    store = SqlCipherRepository.create(tmp_path / "demo", "pw")
    assert not store.path.read_bytes().startswith(b"{")
    # In unit tests this is SQLite, but production rejects this driver unless explicitly enabled.
    with sqlite3.connect(store.path) as conn:
        assert conn.execute("SELECT schema_version FROM schema_info").fetchone() == (2,)


def test_version_one_schema_is_upgraded_with_embedded_secret_manager_default():
    conn = sqlite3.connect(":memory:")
    conn.executescript(
        """
        CREATE TABLE schema_info (
            singleton INTEGER PRIMARY KEY,
            schema_version INTEGER NOT NULL,
            applied_at TEXT NOT NULL,
            key_salt TEXT,
            key_check TEXT
        );
        INSERT INTO schema_info VALUES (1, 1, CURRENT_TIMESTAMP, NULL, NULL);
        CREATE TABLE projects (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL
        );
        INSERT INTO projects VALUES ('project-id', 'demo');
        """
    )

    SqlCipherRepository._upgrade_schema(conn, 1)

    columns = {
        row[1] for row in conn.execute("PRAGMA table_info(projects)").fetchall()
    }
    pointer = conn.execute(
        "SELECT active_secret_manager_kind, active_secret_manager_service_uuid "
        "FROM projects"
    ).fetchone()
    assert {"active_secret_manager_kind", "active_secret_manager_service_uuid"} <= columns
    assert pointer == ("embedded", None)
    assert conn.execute("SELECT schema_version FROM schema_info").fetchone() == (2,)
