from __future__ import annotations

import json
from contextlib import contextmanager
from dataclasses import dataclass
from types import SimpleNamespace

import pytest
from cryptography.fernet import Fernet

from mlox.secret_manager import (
    InMemorySecretManager,
    TinySecretManager,
    get_encrypted_access_keyfile,
    load_secret_manager_from_keyfile,
)
from mlox.utils import _get_encryption_key, decrypt_dict


class _Conn:
    def __init__(self):
        self.is_connected = True


class _Exec:
    def __init__(self):
        self.files = {}

    def fs_create_dir(self, conn, path):
        return None

    def fs_list_files(self, conn, path):
        return [name.split("/")[-1] for name in self.files.keys() if name.startswith(path)]

    def fs_read_file(self, conn, file_path, encoding="utf-8", format="json"):
        return self.files[file_path]

    def fs_touch(self, conn, filepath):
        self.files.setdefault(filepath, b"")

    def fs_write_file(self, conn, filepath, data):
        self.files[filepath] = data


@dataclass
class _Server:
    def __init__(self):
        self.mlox_user = SimpleNamespace(home="/home/mlox")
        self.exec = _Exec()

    @contextmanager
    def get_server_connection(self):
        yield _Conn()


def _encrypt(payload, token):
    key = _get_encryption_key(token)
    return Fernet(key).encrypt(json.dumps(payload).encode("utf-8"))


def test_inmemory_secret_manager_basic_roundtrip():
    sm = InMemorySecretManager()
    sm.save_secret("a", {"x": 1})

    assert sm.is_working()
    assert sm.load_secret("a") == {"x": 1}
    assert sm.list_secrets(keys_only=True) == {"a": None}
    assert sm.get_access_secrets() == {"secrets": {"a": {"x": 1}}}


def test_inmemory_instantiate_secret_manager_prefills_store():
    sm = InMemorySecretManager.instantiate_secret_manager({"secrets": {"k": "v"}})
    assert sm is not None
    assert sm.load_secret("k") == "v"


def test_tiny_secret_manager_list_save_load(monkeypatch):
    server = _Server()
    token = "master"
    existing = _encrypt({"old": True}, token)
    server.exec.files["/secrets/existing.json"] = existing

    monkeypatch.setattr("mlox.secret_manager.dict_to_dataclass", lambda data, hooks: server)

    sm = TinySecretManager(
        server_config_file="ignored",
        secrets_relative_path="secrets",
        master_token=token,
        server_dict={"fake": 1},
        secrets_abs_path="/secrets",
    )

    assert sm.is_working() is True
    assert sm.list_secrets(keys_only=True)["existing"] is None

    sm.save_secret("new", {"hello": "world"})
    assert sm.load_secret("new") == {"hello": "world"}


def test_tiny_secret_manager_load_secret_handles_errors(monkeypatch, caplog):
    server = _Server()
    monkeypatch.setattr("mlox.secret_manager.dict_to_dataclass", lambda data, hooks: server)
    sm = TinySecretManager("", "secrets", "master", server_dict={"x": 1}, secrets_abs_path="/secrets")

    assert sm.load_secret("missing") is None
    assert "Error reading secret" in caplog.text


def test_tiny_secret_manager_instantiate_and_access(monkeypatch):
    server = _Server()
    monkeypatch.setattr("mlox.secret_manager.dict_to_dataclass", lambda data, hooks: server)

    sm = TinySecretManager.instantiate_secret_manager(
        {"keyfile": {"srv": 1}, "secrets_master_token": "pw", "secrets_abs_path": "/secrets"}
    )

    assert sm is not None
    access = sm.get_access_secrets()
    assert access is not None
    assert access["secrets_abs_path"] == "/secrets"


def test_get_encrypted_access_keyfile_roundtrip():
    sm = InMemorySecretManager()
    sm.save_secret("token", "abc")

    encrypted = get_encrypted_access_keyfile(sm, "pw")
    payload = decrypt_dict(encrypted, "pw")

    assert payload["secret_manager_class"].endswith("InMemorySecretManager")


def test_load_secret_manager_from_keyfile_paths(monkeypatch):
    monkeypatch.setattr(
        "mlox.secret_manager.load_from_json",
        lambda keyfile, pw: {
            "secret_manager_class": "mlox.secret_manager.InMemorySecretManager",
            "access_secret": {"secrets": {"z": 1}},
        },
    )

    sm = load_secret_manager_from_keyfile("any", "pw")
    assert sm is not None
    assert sm.load_secret("z") == 1

    monkeypatch.setattr("mlox.secret_manager.load_from_json", lambda *args, **kwargs: (_ for _ in ()).throw(ValueError("bad")))
    with pytest.raises(UnboundLocalError):
        load_secret_manager_from_keyfile("broken", "pw")
