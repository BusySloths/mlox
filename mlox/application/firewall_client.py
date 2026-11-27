"""Local identity for temporary firewall access; never stored in a project."""

from __future__ import annotations

from contextlib import contextmanager
import os
from pathlib import Path
from typing import Iterator
from uuid import UUID, uuid4


@contextmanager
def _exclusive_lock(handle, *, windows: bool | None = None) -> Iterator[None]:
    """Lock the identity file with the native primitive for this platform."""
    if windows is None:
        windows = os.name == "nt"
    if windows:
        # Windows byte-range locks require the requested range to exist.
        # Keep the sentinel in the separate lock file, not in the identity.
        import msvcrt

        handle.seek(0, os.SEEK_END)
        if handle.tell() == 0:
            handle.write(b"\0")
            handle.flush()
        handle.seek(0)
        msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
        try:
            yield
        finally:
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        return

    import fcntl

    fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
    try:
        yield
    finally:
        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def firewall_client_id(*, state_dir: Path | None = None) -> str:
    if state_dir is None:
        configured = os.environ.get("XDG_STATE_HOME")
        state_dir = Path(configured) if configured and Path(configured).is_absolute() else Path.home() / ".local" / "state"
    directory = state_dir / "mlox"
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    # The lock also covers the first creation, so concurrent TUI/CLI processes
    # cannot observe a partially written identifier.
    lock = directory / "firewall-client.lock"
    with lock.open("a+b") as handle:
        os.chmod(lock, 0o600)
        with _exclusive_lock(handle):
            path = directory / "firewall-client-id"
            if path.exists():
                return UUID(path.read_text().strip()).hex
            value = uuid4().hex
            descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(descriptor, "w") as output:
                output.write(value + "\n")
            return value
