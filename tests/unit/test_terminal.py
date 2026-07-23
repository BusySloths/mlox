"""External SSH terminal launcher tests."""

from __future__ import annotations

import shlex
import shutil
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from mlox.server import ServerCapability
from mlox.terminal import (
    SSHLaunchSpec,
    TerminalLaunchError,
    _normalize_private_key,
    _terminal_command,
    _write_launch_files,
    launch_external_ssh_terminal,
    resolve_ssh_launch_spec,
)


def _server(
    credentials: dict, capabilities: set | None = None
) -> SimpleNamespace:
    return SimpleNamespace(
        capabilities=capabilities or set(),
        get_server_connection=lambda: SimpleNamespace(credentials=credentials),
    )


def test_resolve_ssh_spec_uses_effective_managed_credentials() -> None:
    server = _server(
        {
            "host": "10.0.0.5",
            "port": "2202",
            "user": "mlox",
            "pw": "not-exported",
            "private_key": "private-key",
            "passphrase": "not-exported",
        }
    )

    spec = resolve_ssh_launch_spec(server)

    assert spec == SSHLaunchSpec(
        host="10.0.0.5",
        port=2202,
        user="mlox",
        private_key="private-key\n",
    )
    assert not hasattr(spec, "password")
    assert not hasattr(spec, "passphrase")


def test_private_key_normalization_restores_openssh_line_format() -> None:
    assert (
        _normalize_private_key(
            "-----BEGIN OPENSSH PRIVATE KEY-----\r\n"
            "payload\r\n"
            "-----END OPENSSH PRIVATE KEY-----"
        )
        == "-----BEGIN OPENSSH PRIVATE KEY-----\n"
        "payload\n"
        "-----END OPENSSH PRIVATE KEY-----\n"
    )
    assert (
        _normalize_private_key(
            "-----BEGIN OPENSSH PRIVATE KEY-----\\npayload\\n"
            "-----END OPENSSH PRIVATE KEY-----"
        )
        == "-----BEGIN OPENSSH PRIVATE KEY-----\n"
        "payload\n"
        "-----END OPENSSH PRIVATE KEY-----\n"
    )


def test_normalized_encrypted_rsa_key_is_accepted_by_openssh(tmp_path) -> None:
    ssh_keygen = shutil.which("ssh-keygen")
    if not ssh_keygen:
        pytest.skip("ssh-keygen is not installed")

    source_key = tmp_path / "source-key"
    subprocess.run(
        [
            ssh_keygen,
            "-q",
            "-t",
            "rsa",
            "-b",
            "2048",
            "-N",
            "test-passphrase",
            "-f",
            str(source_key),
        ],
        check=True,
    )
    stripped_key = source_key.read_text(encoding="utf-8").rstrip()

    normalized_key = tmp_path / "normalized-key"
    normalized_key.write_text(
        _normalize_private_key(stripped_key),
        encoding="utf-8",
    )
    normalized_key.chmod(0o600)

    result = subprocess.run(
        [
            ssh_keygen,
            "-y",
            "-P",
            "test-passphrase",
            "-f",
            str(normalized_key),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    assert result.stdout.startswith("ssh-rsa ")


def test_resolve_ssh_spec_supports_password_only_fallback() -> None:
    spec = resolve_ssh_launch_spec(
        _server(
            {
                "host": "example.test",
                "port": 22,
                "user": "root",
                "pw": "prompt-for-this",
            }
        )
    )

    assert spec.private_key is None
    assert spec.user == "root"


@pytest.mark.parametrize(
    "capability",
    [ServerCapability.LOCAL, ServerCapability.CONNECTOR],
)
def test_resolve_ssh_spec_rejects_non_ssh_servers(capability) -> None:
    with pytest.raises(TerminalLaunchError, match="does not support SSH"):
        resolve_ssh_launch_spec(_server({}, {capability}))


@pytest.mark.parametrize("port", ["not-a-port", 0, 65536])
def test_resolve_ssh_spec_rejects_invalid_ports(port) -> None:
    with pytest.raises(TerminalLaunchError, match="invalid SSH port"):
        resolve_ssh_launch_spec(
            _server({"host": "example.test", "port": port, "user": "mlox"})
        )


def test_launch_files_use_safe_permissions_and_quoted_arguments() -> None:
    spec = SSHLaunchSpec(
        host="host; touch unsafe",
        port=2202,
        user="user name",
        private_key="private-key",
    )
    temp_dir, script_path = _write_launch_files(spec, "/usr/bin/ssh")
    try:
        key_path = temp_dir / "identity"
        assert key_path.stat().st_mode & 0o777 == 0o600
        assert key_path.read_text(encoding="utf-8") == "private-key"
        assert script_path.stat().st_mode & 0o777 == 0o700

        command_line = next(
            line
            for line in script_path.read_text(encoding="utf-8").splitlines()
            if line.startswith("/usr/bin/ssh ")
        )
        command = shlex.split(command_line)
        assert command == [
            "/usr/bin/ssh",
            "-p",
            "2202",
            "-o",
            "IdentitiesOnly=yes",
            "-i",
            str(key_path),
            "--",
            "user name@host; touch unsafe",
        ]
    finally:
        if temp_dir.exists():
            shutil.rmtree(temp_dir)


def test_password_only_wrapper_omits_identity_file() -> None:
    temp_dir, script_path = _write_launch_files(
        SSHLaunchSpec(host="example.test", port=22, user="root"),
        "/usr/bin/ssh",
    )
    try:
        command = shlex.split(script_path.read_text(encoding="utf-8").splitlines()[-1])
        assert "-i" not in command
        assert not (temp_dir / "identity").exists()
    finally:
        if temp_dir.exists():
            shutil.rmtree(temp_dir)


def test_wrapper_removes_temporary_credentials_after_ssh_exits() -> None:
    temp_dir, script_path = _write_launch_files(
        SSHLaunchSpec(
            host="example.test",
            port=22,
            user="mlox",
            private_key="private-key",
        ),
        "/usr/bin/true",
    )

    subprocess.run([str(script_path)], check=True)

    assert not temp_dir.exists()


def test_wrapper_keeps_terminal_open_when_ssh_fails() -> None:
    temp_dir, script_path = _write_launch_files(
        SSHLaunchSpec(host="example.test", port=22, user="mlox"),
        "/usr/bin/false",
    )
    script = script_path.read_text(encoding="utf-8")

    try:
        assert 'if [ "$status" -ne 0 ]; then' in script
        assert "SSH connection failed" in script
        assert "read -r _ </dev/tty || true" in script
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def test_terminal_commands_for_macos_and_linux(monkeypatch, tmp_path) -> None:
    script_path = tmp_path / "connect.sh"
    monkeypatch.setattr(Path, "is_file", lambda self: True)
    monkeypatch.setattr(Path, "is_dir", lambda self: True)

    terminal, command = _terminal_command(script_path, "darwin")
    assert terminal == "/Applications/iTerm.app"
    assert command[0:2] == ["/usr/bin/osascript", "-e"]
    assert command[-1] == str(script_path)
    assert 'set commandText to " command /bin/sh ' in command[2]
    assert 'set commandText to "/bin/sh ' not in command[2]
    assert "delay 0.2" in command[2]
    assert "quoted form of scriptPath" in command[2]
    assert "com.googlecode.iterm2" in command[2]

    monkeypatch.setattr(
        "mlox.terminal.shutil.which",
        lambda executable: "/usr/bin/x-terminal-emulator"
        if executable == "x-terminal-emulator"
        else None,
    )
    terminal, command = _terminal_command(script_path, "linux")
    assert terminal == "/usr/bin/x-terminal-emulator"
    assert command == [terminal, "-e", str(script_path)]


def test_linux_terminal_command_falls_back_to_common_terminal(
    monkeypatch, tmp_path
) -> None:
    script_path = tmp_path / "connect.sh"

    def fake_which(executable: str) -> str | None:
        if executable == "ghostty":
            return "/usr/bin/ghostty"
        return None

    monkeypatch.setattr("mlox.terminal.shutil.which", fake_which)

    terminal, command = _terminal_command(script_path, "linux")

    assert terminal == "/usr/bin/ghostty"
    assert command == [terminal, "-e", str(script_path)]


def test_macos_terminal_requires_iterm2(monkeypatch, tmp_path) -> None:
    script_path = tmp_path / "connect.sh"
    monkeypatch.setattr(Path, "is_file", lambda self: True)
    monkeypatch.setattr(Path, "is_dir", lambda self: False)

    with pytest.raises(TerminalLaunchError, match="iTerm2 was not found"):
        _terminal_command(script_path, "darwin")


def test_launch_returns_process_metadata_without_exposing_secrets(
    monkeypatch,
) -> None:
    captured: dict = {}

    class FakeProcess:
        pid = 1234

    def fake_which(executable: str) -> str | None:
        return f"/usr/bin/{executable}"

    def fake_popen(command, **kwargs):
        captured["command"] = command
        captured["kwargs"] = kwargs
        return FakeProcess()

    monkeypatch.setattr("mlox.terminal.shutil.which", fake_which)
    monkeypatch.setattr("mlox.terminal.subprocess.Popen", fake_popen)
    server = _server(
        {
            "host": "10.0.0.5",
            "port": 22,
            "user": "mlox",
            "pw": "password-secret",
            "private_key": "private-key-secret",
            "passphrase": "passphrase-secret",
        }
    )

    result = launch_external_ssh_terminal(server, platform="linux")

    assert result.pid == 1234
    assert captured["command"][:2] == ["/usr/bin/x-terminal-emulator", "-e"]
    rendered_command = " ".join(captured["command"])
    assert "password-secret" not in rendered_command
    assert "private-key-secret" not in rendered_command
    assert "passphrase-secret" not in rendered_command

    temp_dir = Path(result.script_path).parent
    if temp_dir.exists():
        shutil.rmtree(temp_dir)


def test_launch_rejects_missing_ssh_client(monkeypatch) -> None:
    monkeypatch.setattr("mlox.terminal.shutil.which", lambda executable: None)

    with pytest.raises(TerminalLaunchError, match="SSH client was not found"):
        launch_external_ssh_terminal(
            _server({"host": "example.test", "port": 22, "user": "mlox"}),
            platform="linux",
        )


def test_launch_rejects_missing_linux_terminal_and_cleans_up(monkeypatch) -> None:
    monkeypatch.setattr(
        "mlox.terminal.shutil.which",
        lambda executable: "/usr/bin/ssh" if executable == "ssh" else None,
    )
    created: list[Path] = []
    original_write = _write_launch_files

    def capture_write(spec, ssh_executable):
        temp_dir, script_path = original_write(spec, ssh_executable)
        created.append(temp_dir)
        return temp_dir, script_path

    monkeypatch.setattr("mlox.terminal._write_launch_files", capture_write)

    with pytest.raises(TerminalLaunchError, match="supported Linux terminal"):
        launch_external_ssh_terminal(
            _server({"host": "example.test", "port": 22, "user": "mlox"}),
            platform="linux",
        )

    assert created
    assert not created[0].exists()


@pytest.mark.parametrize("platform", ["win32", "freebsd"])
def test_launch_rejects_unsupported_platform_and_cleans_up(
    monkeypatch, platform
) -> None:
    monkeypatch.setattr(
        "mlox.terminal.shutil.which",
        lambda executable: "/usr/bin/ssh" if executable == "ssh" else None,
    )
    created: list[Path] = []

    original_write = _write_launch_files

    def capture_write(spec, ssh_executable):
        temp_dir, script_path = original_write(spec, ssh_executable)
        created.append(temp_dir)
        return temp_dir, script_path

    monkeypatch.setattr("mlox.terminal._write_launch_files", capture_write)

    with pytest.raises(TerminalLaunchError, match="not supported"):
        launch_external_ssh_terminal(
            _server({"host": "example.test", "port": 22, "user": "mlox"}),
            platform=platform,
        )

    assert created
    assert not created[0].exists()
