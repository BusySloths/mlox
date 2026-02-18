from __future__ import annotations

from dataclasses import dataclass

import pytest

from mlox import utils


@dataclass
class Child:
    value: int


@dataclass
class Parent:
    name: str
    child: Child


def test_dataclass_to_dict_and_back_with_hook():
    payload = Parent(name="demo", child=Child(value=7))

    as_dict = utils.dataclass_to_dict(payload)
    restored = utils.dict_to_dataclass(as_dict, hooks=[Child])

    assert isinstance(restored, Parent)
    assert restored.child.value == 7


def test_dataclass_to_dict_rejects_non_dataclass():
    with pytest.raises(TypeError):
        utils.dataclass_to_dict({"x": 1})


def test_dict_to_dataclass_requires_class_metadata():
    with pytest.raises(ValueError, match="module and class names"):
        utils.dict_to_dataclass({"foo": "bar"})


def test_encrypt_decrypt_dict_roundtrip():
    data = {"alpha": 1, "nested": {"beta": True}}
    token = utils.encrypt_dict(data, "pw")

    restored = utils.decrypt_dict(token, "pw")

    assert restored == data


def test_save_and_load_json_encrypted_and_plain(tmp_path):
    data = {"hello": "world", "n": 3}
    enc_path = tmp_path / "enc.json"
    plain_path = tmp_path / "plain.json"

    utils.save_to_json(data, str(enc_path), "pw", encrypt=True)
    utils.save_to_json(data, str(plain_path), "pw", encrypt=False)

    # load_from_json expects a cwd-relative path starting with '/'
    rel_enc = "/" + enc_path.relative_to(tmp_path).as_posix()
    rel_plain = "/" + plain_path.relative_to(tmp_path).as_posix()

    with pytest.MonkeyPatch.context() as mp:
        mp.chdir(tmp_path)
        assert utils.load_from_json(rel_enc, "pw", encrypted=True) == data
        assert utils.load_from_json(rel_plain, "pw", encrypted=False) == data


def test_encrypt_existing_json_file_missing_path_logs_error(caplog):
    utils.encrypt_existing_json_file("/does/not/exist.json", "pw")

    assert "File not found" in caplog.text


def test_auto_map_ports_assigns_and_warns(caplog):
    used = [3000, 3001, 3002]
    requested = {"api": 3000, "ui": 3002}

    mapped = utils.auto_map_ports(used, requested, ub=3003, lb=1024)

    assert mapped["api"] == 3003
    assert "ui" not in mapped
    assert "Not all requested ports could be assigned" in caplog.text


def test_generate_pw_length():
    pw = utils.generate_pw(12)
    assert len(pw) == 12
