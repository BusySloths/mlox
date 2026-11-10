"""Transfer encrypted project snapshots through a registered server executor."""
from __future__ import annotations

import os
import fcntl
import posixpath
import re
import shutil
import tempfile
from contextlib import contextmanager
from pathlib import Path
from mlox.project.repository import resolve_project_path

REGISTRY_DIRECTORY = ".mlox/project-registry"


def project_name(value: str) -> str:
    name = value[:-5] if value.endswith(".mlox") else value
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}", name) or name in {".", ".."}:
        raise ValueError("Project name must contain only letters, digits, dots, underscores or hyphens")
    return name


@contextmanager
def _snapshot(path: Path):
    """Copy bytes under SQLite's shared file lock without decrypting them."""
    if not path.is_file():
        raise FileNotFoundError(f"Project does not exist: {path}")
    with tempfile.TemporaryDirectory(prefix="mlox-project-") as directory:
        snapshot = Path(directory) / "snapshot.mlox"
        with path.open("rb") as source:
            # SQLite's POSIX locking protocol: hold a shared lock over its
            # shared-byte range, using the pending byte while acquiring it.
            pending, shared, shared_size = 0x40000000, 0x40000002, 510
            fcntl.lockf(source, fcntl.LOCK_SH, 1, pending)
            try:
                fcntl.lockf(source, fcntl.LOCK_SH, shared_size, shared)
            finally:
                fcntl.lockf(source, fcntl.LOCK_UN, 1, pending)
            if Path(f"{path}-wal").exists():
                raise ValueError("Project has a WAL file; close MLOX and checkpoint the project before pushing")
            before = os.fstat(source.fileno())
            with snapshot.open("xb") as target:
                os.chmod(snapshot, 0o600)
                shutil.copyfileobj(source, target)
            after = os.fstat(source.fileno())
            current = path.stat()
            if ((before.st_dev, before.st_ino) != (current.st_dev, current.st_ino)
                    or (before.st_size, before.st_mtime_ns, before.st_ctime_ns)
                    != (after.st_size, after.st_mtime_ns, after.st_ctime_ns)):
                raise RuntimeError("Project file changed during transfer; close other writers and retry")
        yield snapshot


def push_project(name: str, source: Path, *, server, force: bool = False) -> dict:
    name = project_name(name)
    with _snapshot(source) as snapshot, server.get_server_connection() as connection:
        executor = server.exec
        directory = posixpath.join(executor.fs_home_directory(connection), REGISTRY_DIRECTORY)
        destination = posixpath.join(directory, name + ".mlox")
        size_bytes = snapshot.stat().st_size
        published = executor.fs_publish_private_file(connection, str(snapshot), destination, force=force)
    if not published:
        raise FileExistsError(f"Project {name!r} already exists in the registry. Use --force to replace it.")
    return {"name": name, "remote_path": destination, "size_bytes": size_bytes}


def _replace_local_project(temporary: Path, destination: Path) -> None:
    """Replace a local project only while no SQLite transaction holds a lock."""
    for suffix in ("-wal", "-shm", "-journal"):
        if Path(f"{destination}{suffix}").exists():
            raise RuntimeError(f"Cannot overwrite {destination}: SQLite sidecar {suffix} exists. Close MLOX first.")
    try:
        fd = os.open(destination, os.O_RDWR | getattr(os, "O_NOFOLLOW", 0))
    except FileNotFoundError:
        try:
            os.link(temporary, destination)
        except FileExistsError:
            _replace_local_project(temporary, destination)
        return
    try:
        try:
            fcntl.lockf(fd, fcntl.LOCK_EX | fcntl.LOCK_NB, 512, 0x40000000)
        except BlockingIOError as exc:
            raise RuntimeError(f"Cannot overwrite {destination}: project is in use. Close MLOX first.") from exc
        for suffix in ("-wal", "-shm", "-journal"):
            if Path(f"{destination}{suffix}").exists():
                raise RuntimeError(f"Cannot overwrite {destination}: SQLite sidecar {suffix} exists. Close MLOX first.")
        locked = os.fstat(fd)
        current = destination.stat()
        if (locked.st_dev, locked.st_ino) != (current.st_dev, current.st_ino):
            raise RuntimeError("Local project changed during pull; retry the operation")
        os.replace(temporary, destination)
    finally:
        os.close(fd)


def pull_project(name: str, directory: Path | None = None, *, server, force: bool = False) -> dict:
    name = project_name(name)
    directory = directory or resolve_project_path(name).parent
    directory.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(prefix=".mlox-pull-", dir=directory, delete=False) as target:
        temporary = Path(target.name)
    try:
        with server.get_server_connection() as connection:
            executor = server.exec
            remote = posixpath.join(executor.fs_home_directory(connection), REGISTRY_DIRECTORY, name + ".mlox")
            executor.fs_download(connection, remote, str(temporary))
        size_bytes = temporary.stat().st_size
        with temporary.open("rb") as downloaded:
            os.fsync(downloaded.fileno())
        if force:
            destination = directory / (name + ".mlox")
            _replace_local_project(temporary, destination)
        else:
            for suffix in range(1000000):
                filename = name + (f"_{suffix}" if suffix else "") + ".mlox"
                destination = directory / filename
                try:
                    os.link(temporary, destination)
                    break
                except FileExistsError:
                    continue
            else:
                raise FileExistsError("Could not find an available project filename")
    finally:
        temporary.unlink(missing_ok=True)
    return {"name": name, "path": str(destination), "remote_path": remote, "size_bytes": size_bytes}
