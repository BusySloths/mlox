import json
from dataclasses import dataclass
from io import BytesIO
from unittest.mock import ANY, MagicMock, call

import pytest
from fabric import Connection  # type: ignore

from mlox.executors import UbuntuTaskExecutor


@dataclass
class FakeResult:
    stdout: str
    stderr: str = ""
    exited: int = 0
    ok: bool = True


@pytest.fixture
def executor() -> UbuntuTaskExecutor:
    return UbuntuTaskExecutor()


@pytest.fixture
def mock_connection() -> MagicMock:
    conn = MagicMock(spec=Connection)
    conn.host = "test_host"
    conn.user = "test_user"
    return conn


def test_run_ad_hoc_task(mock_connection: MagicMock, executor: UbuntuTaskExecutor) -> None:
    mock_connection.run.return_value = FakeResult(stdout="test_output")
    result = executor.run_ad_hoc_task(mock_connection, "test_command")
    assert result == "test_output"
    mock_connection.run.assert_called_once_with("test_command", hide=True)

    mock_connection.sudo.return_value = FakeResult(stdout="sudo_output")
    result_sudo = executor.run_ad_hoc_task(
        mock_connection, "test_sudo_command", sudo=True
    )
    assert result_sudo == "sudo_output"
    mock_connection.sudo.assert_called_once_with(
        "test_sudo_command", hide="stderr", pty=False
    )


def test_sys_disk_free(mock_connection: MagicMock, executor: UbuntuTaskExecutor) -> None:
    mock_connection.run.side_effect = [
        FakeResult(stdout="Linux"),
        FakeResult(stdout="25%"),
    ]
    result = executor.sys_disk_free(mock_connection)
    assert result == 25
    mock_connection.run.assert_has_calls(
        [
            call("uname -s", hide=True),
            call("df -h / | tail -n1 | awk '{print $5}'", hide=True),
        ]
    )


def test_fs_create_dir(mock_connection: MagicMock, executor: UbuntuTaskExecutor) -> None:
    executor.fs_create_dir(mock_connection, "/test/path")
    mock_connection.run.assert_called_once_with("mkdir -p /test/path", hide=True)


def test_fs_delete_dir(mock_connection: MagicMock, executor: UbuntuTaskExecutor) -> None:
    executor.fs_delete_dir(mock_connection, "/test/path")
    mock_connection.sudo.assert_called_once_with(
        "rm -rf /test/path", hide="stderr", pty=False
    )


def test_fs_append_line(mock_connection: MagicMock, executor: UbuntuTaskExecutor) -> None:
    executor.fs_append_line(mock_connection, "/test/file", "test_line")
    mock_connection.run.assert_any_call("touch /test/file", hide=True)
    mock_connection.run.assert_called_with("echo 'test_line' >> /test/file", hide=True)


def test_fs_create_empty_file(
    mock_connection: MagicMock, executor: UbuntuTaskExecutor
) -> None:
    executor.fs_create_empty_file(mock_connection, "/test/file")
    mock_connection.run.assert_called_once_with("echo -n >| /test/file", hide=True)


def test_fs_find_and_replace(
    mock_connection: MagicMock, executor: UbuntuTaskExecutor
) -> None:
    executor.fs_find_and_replace(mock_connection, "/test/file", "old", "new")
    mock_connection.run.assert_called_once_with(
        "sed -i 's!old!new!g' /test/file",
        hide=True,
    )


def test_fs_write_file(mock_connection: MagicMock, executor: UbuntuTaskExecutor) -> None:
    executor.fs_write_file(mock_connection, "/test/file", "test_content")
    mock_connection.put.assert_called_once_with(ANY, remote="/test/file")
    file_like_object = mock_connection.put.call_args[0][0]
    assert isinstance(file_like_object, BytesIO)
    assert file_like_object.getvalue() == b"test_content"


def test_fs_read_file(mock_connection: MagicMock, executor: UbuntuTaskExecutor) -> None:
    def mock_get(path: str, buffer: BytesIO) -> FakeResult:
        buffer.write(b"test_content")
        return FakeResult(stdout="")

    mock_connection.get.side_effect = mock_get
    result = executor.fs_read_file(mock_connection, "/test/file", format="txt")
    assert result == "test_content"
    mock_connection.get.assert_called_once()


def test_fs_list_files(mock_connection: MagicMock, executor: UbuntuTaskExecutor) -> None:
    mock_connection.run.return_value = FakeResult(stdout="file1\nfile2\ndir1")
    result = executor.fs_list_files(mock_connection, "/test/path")
    assert result == ["file1", "file2", "dir1"]


def test_docker_service_state(
    mock_connection: MagicMock, executor: UbuntuTaskExecutor
) -> None:
    mock_connection.sudo.return_value = FakeResult(stdout="running")
    state = executor.docker_service_state(mock_connection, "svc1")
    assert state == "running"
    mock_connection.sudo.assert_called_once_with(
        "docker inspect --format '{{.State.Status}}' svc1", hide="stderr", pty=False
    )


def test_docker_all_service_states(
    mock_connection: MagicMock, executor: UbuntuTaskExecutor
) -> None:
    mock_connection.sudo.side_effect = [
        FakeResult(stdout="id1\nid2"),
        FakeResult(
            stdout=json.dumps(
                [
                    {"Name": "/svc1", "State": {"Status": "running"}},
                    {"Name": "/svc2", "State": {"Status": "exited"}},
                ]
            )
        ),
    ]
    result = executor.docker_all_service_states(mock_connection)
    assert result == {
        "svc1": {"Status": "running"},
        "svc2": {"Status": "exited"},
    }
    mock_connection.sudo.assert_has_calls(
        [
            call("docker ps -aq", hide="stderr", pty=False),
            call("docker inspect id1 id2", hide="stderr", pty=False),
        ]
    )
