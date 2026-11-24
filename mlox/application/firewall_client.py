"""Local identity for temporary firewall access; never stored in a project."""

from __future__ import annotations

import fcntl
import os
from pathlib import Path
from uuid import UUID, uuid4


def firewall_client_id(*, state_dir: Path | None = None) -> str:
    if state_dir is None:
        configured = os.environ.get("XDG_STATE_HOME")
        state_dir = Path(configured) if configured and Path(configured).is_absolute() else Path.home() / ".local" / "state"
    directory = state_dir / "mlox"
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    # The lock also covers the first creation, so concurrent TUI/CLI processes
    # cannot observe a partially written identifier.
    lock = directory / "firewall-client.lock"
    with lock.open("a+") as handle:
        os.chmod(lock, 0o600)
        fcntl.flock(handle, fcntl.LOCK_EX)
        path = directory / "firewall-client-id"
        if path.exists():
            return UUID(path.read_text().strip()).hex
        value = uuid4().hex
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "w") as output:
            output.write(value + "\n")
        return value
