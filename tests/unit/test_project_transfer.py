from pathlib import Path
import os
import json
import subprocess
import sys
from contextlib import nullcontext
from types import SimpleNamespace

import pytest
from typer.testing import CliRunner

from mlox import cli
from mlox.project import ProjectWorkspace
from mlox.project import transfer


@pytest.fixture
def registry(monkeypatch, tmp_path):
    from mlox.executors import UbuntuTaskExecutor
    from mlox.servers.local.local import LocalConnection
    remote = tmp_path / "remote"
    remote.mkdir()
    executor = UbuntuTaskExecutor()
    monkeypatch.setattr(executor, "fs_home_directory", lambda connection: str(remote))
    connection = LocalConnection(remote, "localhost", "test")
    server = SimpleNamespace(exec=executor, get_server_connection=lambda: nullcontext(connection), home=remote)
    monkeypatch.setattr("mlox.cli.commands.project._managed_transfer_server", lambda *args: server)
    return server


def test_push_force_and_pull_collision(registry, tmp_path):
    path = tmp_path / "sales.mlox"
    workspace = ProjectWorkspace.create(path, "password")
    first = transfer.push_project("sales", path, server=registry)
    assert first["size_bytes"] == path.stat().st_size
    original = Path(first["remote_path"]).read_bytes()
    workspace.descr = "updated"
    workspace.commit()
    with pytest.raises(FileExistsError, match="--force"):
        transfer.push_project("sales", path, server=registry)
    assert Path(first["remote_path"]).read_bytes() == original
    second = transfer.push_project("sales", path, server=registry, force=True)
    assert not list(Path(second["remote_path"]).parent.glob("*.backup-*.mlox"))
    assert Path(second["remote_path"]).stat().st_mode & 0o777 == 0o600
    pulled = transfer.pull_project("sales", tmp_path, server=registry)
    assert pulled["size_bytes"] == Path(second["remote_path"]).stat().st_size
    assert Path(pulled["path"]).name == "sales_1.mlox"
    assert ProjectWorkspace.open(pulled["path"], "password").descr == "updated"
    assert transfer.pull_project("sales", tmp_path, server=registry)["path"].endswith("sales_2.mlox")


def test_pull_force_replaces_exact_file(registry, tmp_path):
    path = tmp_path / "sales.mlox"
    path.write_bytes(b"remote version")
    transfer.push_project("sales", path, server=registry)
    path.write_bytes(b"local version")
    result = transfer.pull_project("sales", tmp_path, server=registry, force=True)
    assert result["path"] == str(path)
    assert path.read_bytes() == b"remote version"
    assert not (tmp_path / "sales_1.mlox").exists()


@pytest.mark.parametrize("suffix", ["-wal", "-shm", "-journal"])
def test_pull_force_rejects_sqlite_sidecars(registry, tmp_path, suffix):
    path = tmp_path / "sales.mlox"
    path.write_bytes(b"remote version")
    transfer.push_project("sales", path, server=registry)
    path.write_bytes(b"local version")
    (tmp_path / f"sales.mlox{suffix}").write_bytes(b"pending")
    with pytest.raises(RuntimeError, match="sidecar"):
        transfer.pull_project("sales", tmp_path, server=registry, force=True)
    assert path.read_bytes() == b"local version"
    assert not list(tmp_path.glob(".mlox-pull-*"))


def test_pull_force_rejects_active_sqlite_transaction(registry, tmp_path):
    path = tmp_path / "sales.mlox"
    ProjectWorkspace.create(path, "password")
    transfer.push_project("sales", path, server=registry)
    original = path.read_bytes()
    code = ("import sqlite3,sys; c=sqlite3.connect(sys.argv[1]); "
            "c.execute('BEGIN EXCLUSIVE'); print('ready', flush=True); sys.stdin.readline()")
    process = subprocess.Popen([sys.executable, "-c", code, str(path)], stdin=subprocess.PIPE,
                               stdout=subprocess.PIPE, text=True)
    try:
        assert process.stdout.readline().strip() == "ready"
        with pytest.raises(RuntimeError, match="in use"):
            transfer.pull_project("sales", tmp_path, server=registry, force=True)
        assert path.read_bytes() == original
        assert not list(tmp_path.glob(".mlox-pull-*"))
    finally:
        process.stdin.write("\n")
        process.stdin.flush()
        process.communicate(timeout=5)


def test_push_copies_file_without_project_password(registry, tmp_path):
    path = tmp_path / "opaque.mlox"
    path.write_bytes(b"encrypted-looking opaque file")
    result = transfer.push_project("opaque", path, server=registry)
    assert Path(result["remote_path"]).read_bytes() == path.read_bytes()


def test_push_rejects_wal_sidecar(registry, tmp_path):
    path = tmp_path / "lake.mlox"
    path.write_bytes(b"project bytes")
    (tmp_path / "lake.mlox-wal").write_bytes(b"uncheckpointed data")
    with pytest.raises(ValueError, match="WAL"):
        transfer.push_project("lake", path, server=registry)


def test_snapshot_preserves_sqlcipher_encryption(registry, tmp_path, monkeypatch):
    pytest.importorskip("sqlcipher3")
    monkeypatch.delenv("MLOX_ALLOW_PLAINTEXT_SQLITE", raising=False)
    path = tmp_path / "encrypted.mlox"
    ProjectWorkspace.create(path, "password")
    result = transfer.push_project("encrypted", path, server=registry)
    assert not Path(result["remote_path"]).read_bytes().startswith(b"SQLite format 3")
    local = transfer.pull_project("encrypted", tmp_path, server=registry)
    assert ProjectWorkspace.open(local["path"], "password").name == "encrypted"


def test_rejects_path_traversal_and_failed_download_cleans_temporary(registry, tmp_path):
    with pytest.raises(ValueError):
        transfer.pull_project("../sales", tmp_path, server=registry)
    with pytest.raises(FileNotFoundError):
        transfer.pull_project("missing", tmp_path, server=registry)
    assert not list(tmp_path.glob(".mlox-pull-*"))


def test_executor_keeps_existing_file_when_upload_fails(registry, tmp_path, monkeypatch):
    source = tmp_path / "new content"
    source.write_bytes(b"new")
    directory = registry.home / "directory with spaces"
    directory.mkdir()
    destination = directory / "project.mlox"
    destination.write_bytes(b"old")
    connection = registry.get_server_connection().__enter__()
    monkeypatch.setattr(connection, "put", lambda *args: (_ for _ in ()).throw(OSError("upload failed")))
    with pytest.raises(OSError, match="upload failed"):
        registry.exec.fs_publish_private_file(connection, str(source), str(destination))
    assert destination.read_bytes() == b"old"
    assert not list(directory.glob(".upload-*"))


def test_pull_requires_existing_project(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("MLOX_PROJECT_PATH", raising=False)
    monkeypatch.delenv("MLOX_PROJECT_NAME", raising=False)
    result = CliRunner().invoke(cli.app, ["project", "pull", "--ip", "server", "--name", "sales"])
    assert result.exit_code != 0
    assert "project" in result.output.lower()


def test_cli_commands_use_named_and_current_project(registry, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("MLOX_PROJECT_PATH", "sales.mlox")
    monkeypatch.setenv("MLOX_PROJECT_PASSWORD", "password")
    ProjectWorkspace.create("sales", "password")
    runner = CliRunner()
    result = runner.invoke(cli.app, ["project", "push", "--ip", "example"])
    assert result.exit_code == 0, result.output
    assert "MB)" in result.output
    result = runner.invoke(cli.app, ["project", "push", "--ip", "example"])
    assert result.exit_code != 0 and "--force" in result.output
    assert "Traceback" not in result.output and "FileExistsError" not in result.output
    result = runner.invoke(cli.app, ["--output", "json", "project", "pull", "--ip", "example", "--name", "sales"])
    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["data"]["size_bytes"] > 0
    assert (tmp_path / "sales_1.mlox").exists()
    result = runner.invoke(cli.app, ["project", "pull", "--ip", "example", "--name", "sales", "--force"])
    assert result.exit_code == 0, result.output
    assert not (tmp_path / "sales_2.mlox").exists()
    result = runner.invoke(cli.app, ["project", "push", "--ip", "example", "--project", "sales_1.mlox", "--name", "sales", "--force"])
    assert result.exit_code == 0, result.output
    assert not list((registry.home / ".mlox" / "project-registry").glob("sales.backup-*.mlox"))


def test_push_named_project_needs_only_current_project_password(registry, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    ProjectWorkspace.create("current", "current-password")
    ProjectWorkspace.create("airml", "airml-password")
    monkeypatch.setenv("MLOX_PROJECT_PATH", "current.mlox")
    monkeypatch.setenv("MLOX_PROJECT_PASSWORD", "current-password")
    monkeypatch.delenv("MLOX_PROJECT_PASSWORD_AIRML", raising=False)
    captured = []
    def resolve_server(path, password, identifier):
        captured.append((path, password, identifier))
        return registry
    monkeypatch.setattr("mlox.cli.commands.project._managed_transfer_server", resolve_server)
    result = CliRunner().invoke(cli.app, ["project", "push", "--ip", "sartre", "--name", "airml"])
    assert result.exit_code == 0, result.output
    assert captured == [(tmp_path / "current.mlox", "current-password", "sartre")]
    pulled = transfer.pull_project("airml", tmp_path, server=registry)
    assert ProjectWorkspace.open(pulled["path"], "airml-password").name == "airml"


def test_resolves_managed_server_name_and_rejects_ambiguous(monkeypatch, tmp_path):
    from mlox.cli.commands.project import _managed_transfer_server
    from mlox.infra import Infrastructure
    from mlox.project.repository import SqlCipherRepository

    server = SimpleNamespace(ip="192.0.2.1")
    infra = Infrastructure()
    infra.bundles = [SimpleNamespace(name="sartre", server=server)]
    monkeypatch.setattr(SqlCipherRepository, "load", lambda self: SimpleNamespace(infrastructure=infra))
    assert _managed_transfer_server(tmp_path / "test.mlox", "password", "sartre") is server
    assert _managed_transfer_server(tmp_path / "test.mlox", "password", "2.1") is server
    with pytest.raises(ValueError, match="not registered"):
        _managed_transfer_server(tmp_path / "test.mlox", "password", "ssh-alias")
    infra.bundles.append(SimpleNamespace(name="sartre", server=SimpleNamespace(ip="192.0.2.2")))
    with pytest.raises(ValueError, match="ambiguous"):
        _managed_transfer_server(tmp_path / "test.mlox", "password", "sartre")
