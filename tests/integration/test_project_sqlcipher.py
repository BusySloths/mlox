"""Encryption boundary test; requires the production SQLCipher driver."""
import sqlite3

import pytest

from mlox.project.repository import SqlCipherRepository

pytestmark = pytest.mark.integration


def test_sqlcipher_project_cannot_be_read_by_plain_sqlite(tmp_path, monkeypatch):
    pytest.importorskip("sqlcipher3")
    monkeypatch.delenv("MLOX_ALLOW_PLAINTEXT_SQLITE", raising=False)
    store = SqlCipherRepository.create(tmp_path / "encrypted", "correct horse battery staple")
    with pytest.raises(sqlite3.DatabaseError):
        with sqlite3.connect(store.path) as conn:
            conn.execute("SELECT * FROM projects").fetchall()
    assert SqlCipherRepository(store.path, "correct horse battery staple").open().integrity_check()
