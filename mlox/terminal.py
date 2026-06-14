"""Launch external terminals for interactive SSH sessions."""

from __future__ import annotations

import shlex
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from mlox.server import ServerCapability


class TerminalLaunchError(RuntimeError):
    """Raised when an external SSH terminal cannot be launched."""


@dataclass(frozen=True)
class SSHLaunchSpec:
    """Non-password SSH details required for an interactive terminal."""

    host: str
    port: int
    user: str
    private_key: str | None = None


@dataclass(frozen=True)
class TerminalLaunchResult:
    """Metadata for a successfully launched terminal process."""

    pid: int
    terminal: str
    script_path: str


def _normalize_private_key(private_key: str) -> str:
    """Restore the line-oriented format required by OpenSSH."""

    normalized = private_key.replace("\r\n", "\n").replace("\r", "\n")
    if "\n" not in normalized and "\\n" in normalized:
        normalized = normalized.replace("\\n", "\n")
    return normalized.strip() + "\n"


def _server_capability_names(server: object) -> set[str]:
    return {
        capability.value if hasattr(capability, "value") else str(capability)
        for capability in getattr(server, "capabilities", set())
    }


def resolve_ssh_launch_spec(server: object) -> SSHLaunchSpec:
    """Resolve the managed SSH identity without opening a connection."""

    capabilities = _server_capability_names(server)
    unsupported = {
        ServerCapability.LOCAL.value,
        ServerCapability.CONNECTOR.value,
    }
    if capabilities & unsupported:
        raise TerminalLaunchError("The selected server does not support SSH.")

    try:
        connection = server.get_server_connection()
    except Exception as exc:
        raise TerminalLaunchError(
            "Could not resolve SSH credentials for the selected server."
        ) from exc

    credentials = getattr(connection, "credentials", None)
    if not isinstance(credentials, Mapping):
        raise TerminalLaunchError("The selected server does not provide SSH credentials.")

    host = str(credentials.get("host", "")).strip()
    user = str(credentials.get("user", "")).strip()
    raw_port = credentials.get("port", 22)
    try:
        port = int(raw_port)
    except (TypeError, ValueError) as exc:
        raise TerminalLaunchError("The selected server has an invalid SSH port.") from exc

    if not host or not user:
        raise TerminalLaunchError("The selected server has incomplete SSH credentials.")
    if port < 1 or port > 65535:
        raise TerminalLaunchError("The selected server has an invalid SSH port.")

    private_key = credentials.get("private_key")
    if private_key is not None:
        private_key = str(private_key)
        if private_key.strip():
            private_key = _normalize_private_key(private_key)
        else:
            private_key = None

    return SSHLaunchSpec(
        host=host,
        port=port,
        user=user,
        private_key=private_key,
    )


def _ssh_command(
    spec: SSHLaunchSpec, key_path: Path | None, ssh_executable: str = "ssh"
) -> list[str]:
    command = [
        ssh_executable,
        "-p",
        str(spec.port),
        "-o",
        "IdentitiesOnly=yes",
    ]
    if key_path:
        command.extend(["-i", str(key_path)])
    command.extend(["--", f"{spec.user}@{spec.host}"])
    return command


def _write_launch_files(
    spec: SSHLaunchSpec, ssh_executable: str = "ssh"
) -> tuple[Path, Path]:
    temp_dir = Path(tempfile.mkdtemp(prefix="mlox-ssh-"))
    key_path: Path | None = None
    try:
        if spec.private_key:
            key_path = temp_dir / "identity"
            key_path.write_text(spec.private_key, encoding="utf-8")
            key_path.chmod(0o600)

        script_path = temp_dir / "connect.sh"
        ssh_command = shlex.join(_ssh_command(spec, key_path, ssh_executable))
        script_path.write_text(
            "#!/bin/sh\n"
            "cleanup() {\n"
            f"  rm -rf -- {shlex.quote(str(temp_dir))}\n"
            "}\n"
            "trap cleanup EXIT HUP INT TERM\n"
            f"{ssh_command}\n"
            "status=$?\n"
            "cleanup\n"
            "trap - EXIT HUP INT TERM\n"
            "if [ \"$status\" -ne 0 ]; then\n"
            '  printf \'\\nSSH connection failed (exit status %s).\\n\' "$status"\n'
            "  printf 'Press Enter to close this terminal... '\n"
            "  read -r _ </dev/tty || true\n"
            "fi\n"
            'exit "$status"\n',
            encoding="utf-8",
        )
        script_path.chmod(0o700)
        return temp_dir, script_path
    except Exception:
        shutil.rmtree(temp_dir, ignore_errors=True)
        raise


def _terminal_command(script_path: Path, platform: str) -> tuple[str, list[str]]:
    if platform == "darwin":
        terminal = "/Applications/iTerm.app"
        opener = "/usr/bin/open"
        if not Path(opener).is_file():
            raise TerminalLaunchError("The macOS application launcher was not found.")
        if not Path(terminal).is_dir():
            raise TerminalLaunchError("iTerm2 was not found in /Applications.")
        return terminal, [opener, "-a", "iTerm", str(script_path)]

    if platform.startswith("linux"):
        terminal = shutil.which("x-terminal-emulator")
        if not terminal:
            raise TerminalLaunchError("x-terminal-emulator was not found.")
        return terminal, [terminal, "-e", str(script_path)]

    raise TerminalLaunchError(
        f"External SSH terminals are not supported on {platform or 'this platform'}."
    )


def launch_external_ssh_terminal(
    server: object,
    *,
    platform: str | None = None,
) -> TerminalLaunchResult:
    """Launch an external terminal connected to ``server`` over SSH."""

    spec = resolve_ssh_launch_spec(server)
    ssh_executable = shutil.which("ssh")
    if not ssh_executable:
        raise TerminalLaunchError("The system SSH client was not found.")

    temp_dir, script_path = _write_launch_files(spec, ssh_executable)
    try:
        terminal, command = _terminal_command(script_path, platform or sys.platform)
        process = subprocess.Popen(
            command,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
    except Exception as exc:
        shutil.rmtree(temp_dir, ignore_errors=True)
        if isinstance(exc, TerminalLaunchError):
            raise
        raise TerminalLaunchError("Failed to launch the external terminal.") from exc

    return TerminalLaunchResult(
        pid=process.pid,
        terminal=terminal,
        script_path=str(script_path),
    )
