import pytest

from fabric import Connection, Result
from unittest.mock import MagicMock, call, ANY
from io import BytesIO

from mlox.remote import (
    open_connection,
    close_connection,
    exec_command,
    sys_disk_free,
    fs_create_dir,
    fs_delete_dir,
    fs_append_line,
    fs_create_empty_file,
    fs_find_and_replace,
    fs_write_file,
    fs_read_file,
    fs_list_files,
)


@pytest.fixture
def mock_connection():
    conn = MagicMock(spec=Connection)
    conn.host = "test_host"
    conn.user = "test_user"
    return conn


def test_exec_command(mock_connection):
    mock_connection.run.return_value = Result(
        stdout="test_output", stderr="", exited=0, connection=mock_connection
    )
    result = exec_command(mock_connection, "test_command")
    assert result == "test_output"
    mock_connection.run.assert_called_once_with("test_command", hide=True)

    mock_connection.sudo.return_value = Result(
        stdout="sudo_output", stderr="", exited=0, connection=mock_connection
    )
    result_sudo = exec_command(mock_connection, "test_sudo_command", sudo=True)
    assert result_sudo == "sudo_output"
    mock_connection.sudo.assert_called_once_with(
        "test_sudo_command", hide="stderr", pty=False
    )


def test_sys_disk_free(mock_connection):
    # The function first calls 'uname -s', then 'df -h ...'
    mock_connection.run.side_effect = [
        Result(stdout="Linux", stderr="", exited=0, connection=mock_connection),
        Result(stdout="25%", stderr="", exited=0, connection=mock_connection),
    ]
    result = sys_disk_free(mock_connection)
    assert result == 25
    calls = [
        call("uname -s", hide=True),
        call("df -h / | tail -n1 | awk '{print $5}'", hide=True),
    ]
    mock_connection.run.assert_has_calls(calls)


def test_fs_create_dir(mock_connection):
    fs_create_dir(mock_connection, "/test/path")
    mock_connection.run.assert_called_once_with("mkdir -p /test/path", hide=True)


def test_fs_delete_dir(mock_connection):
    fs_delete_dir(mock_connection, "/test/path")
    mock_connection.sudo.assert_called_once_with(
        "rm -rf /test/path", hide="stderr", pty=False
    )


def test_fs_append_line(mock_connection):
    fs_append_line(mock_connection, "/test/file", "test_line")
    mock_connection.run.assert_any_call("touch /test/file", hide=True)
    mock_connection.run.assert_called_with("echo 'test_line' >> /test/file", hide=True)


def test_fs_create_empty_file(mock_connection):
    fs_create_empty_file(mock_connection, "/test/file")
    mock_connection.run.assert_called_once_with("echo -n >| /test/file", hide=True)


def test_fs_find_and_replace(mock_connection):
    fs_find_and_replace(mock_connection, "/test/file", "old", "new")
    mock_connection.run.assert_called_once_with(
        "sed -i 's!old!new!g' /test/file",
        hide=True,
    )


def test_fs_write_file(mock_connection):
    fs_write_file(mock_connection, "/test/file", "test_content")
    mock_connection.put.assert_called_once_with(ANY, remote="/test/file")

    # Verify the content of the BytesIO object passed to put
    file_like_object = mock_connection.put.call_args[0][0]
    assert isinstance(file_like_object, BytesIO)
    assert file_like_object.getvalue() == b"test_content"


def test_fs_read_file(mock_connection):
    # Mock conn.get to simulate writing content to the file-like object
    def mock_get(remote, local):
        local.write(b"test_content")
        # The actual return of conn.get is a Result object, not used by fs_read_file
        return Result(stdout="", stderr="", exited=0, connection=mock_connection)

    mock_connection.get.side_effect = mock_get
    result = fs_read_file(mock_connection, "/test/file", format="txt")
    assert result == "test_content"
    mock_connection.get.assert_called_once_with("/test/file", ANY)


def test_fs_list_files(mock_connection):
    mock_connection.run.return_value = Result(
        stdout="file1\nfile2\ndir1", stderr="", exited=0, connection=mock_connection
    )
    result = fs_list_files(mock_connection, "/test/path")
    assert result == ["file1", "file2", "dir1"]
