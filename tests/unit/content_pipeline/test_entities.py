from __future__ import annotations

import json
import subprocess

import pytest

from scripts.content_pipeline import entities


SERVERS = [
    {"ip": "194.163.165.102", "uuid": "u1", "backend": "docker"},
    {"ip": "connector-02", "uuid": "u2", "backend": "connector"},
]
SERVICES = [
    {
        "name": "Github:git@github.com:acme-sw-ag/acme-ml.git@194.163.165.102",
        "server_ip": "194.163.165.102",
        "urls": ["Redis IP: 161.97.91.16", "https://mlflow.acme.example:8443/"],
        "labels": ["Redis"],
    },
    {
        "name": "repo",
        "urls": ["https://github.com/jdoe/tool.git", "http://127.0.0.1:5000"],
        "bindings": {"owner": "ops@acme.example"},
    },
]


def test_extract_collects_ips_git_owners_hosts_and_emails():
    found = entities.extract(SERVERS, SERVICES)
    assert "194.163.165.102" in found
    assert "161.97.91.16" in found
    assert "acme-sw-ag" in found and "acme-ml" in found
    assert "jdoe" in found and "tool" not in found  # short names are too generic
    assert "mlflow.acme.example" in found
    assert "ops@acme.example" in found


def test_extract_skips_loopback_docs_ranges_and_public_hosts():
    found = entities.extract(SERVERS, SERVICES)
    assert "127.0.0.1" not in found
    assert "github.com" not in found
    assert not any(e.startswith("198.51.100.") for e in entities.extract(
        [{"ip": "198.51.100.7"}], []))


def test_extract_is_sorted_and_unique():
    found = entities.extract(SERVERS + SERVERS, SERVICES)
    assert found == sorted(set(found), key=str.lower)


def test_from_mlox_cli_passes_password_via_env(monkeypatch):
    calls = []

    def fake_run(cmd, **kw):
        calls.append((cmd, kw))
        key = "servers" if cmd[-2] == "server" else "services"
        payload = {"success": True, "data": {key: SERVERS if key == "servers" else SERVICES}}
        return subprocess.CompletedProcess(cmd, 0, json.dumps(payload), "")

    monkeypatch.setattr(entities.subprocess, "run", fake_run)
    found = entities.from_mlox_cli("demo.mlox", password="s3cret")
    assert "194.163.165.102" in found
    for cmd, kw in calls:
        assert "s3cret" not in " ".join(cmd)
        assert kw["env"]["MLOX_PROJECT_PASSWORD"] == "s3cret"
        assert kw["env"]["MLOX_PROJECT_PATH"] == "demo.mlox"


def test_from_mlox_cli_raises_on_failed_command(monkeypatch):
    def fake_run(cmd, **kw):
        return subprocess.CompletedProcess(cmd, 1, json.dumps({"success": False}), "boom")

    monkeypatch.setattr(entities.subprocess, "run", fake_run)
    with pytest.raises(RuntimeError, match="server list"):
        entities.from_mlox_cli("demo.mlox", password="x")


def test_save_and_load_roundtrip(tmp_path):
    entities.save(tmp_path, ["b", "a"])
    assert entities.load(tmp_path) == ["a", "b"]
    assert entities.load(tmp_path / "missing") == []
