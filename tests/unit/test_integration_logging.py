"""Exercise real pytest capture, including subprocess output and fixture failures."""

import os
from pathlib import Path
import subprocess
import sys


def test_quiet_integration_logs_capture_all_phases(tmp_path):
    suite = tmp_path / "suite"
    suite.mkdir()
    (suite / "pytest.ini").write_text("[pytest]\nmarkers = integration\nlog_cli = true\n")
    (suite / "test_example.py").write_text('''
import logging
import os
import pytest

pytestmark = pytest.mark.integration

@pytest.fixture
def resource():
    print("setup output")
    yield
    print("teardown output")

def test_output(resource):
    print("call output")
    os.write(2, b"native stderr output\\n")
    logging.warning("logged warning")
    assert False, "intentional failure"

@pytest.fixture
def broken():
    print("failed setup output")
    raise RuntimeError("setup broke")

def test_setup_failure(broken):
    pass

def test_success():
    from fabric import Connection
    connection = Connection("example.invalid")
    assert connection.config.run.in_stream is False
    assert connection.local("printf fabric-output", hide=True).stdout == "fabric-output"

''')
    root = Path(__file__).resolve().parents[2]
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "-p", "tests.integration_logging",
         "-p", "no:sugar", "-s", "-q", "--integration-log-dir", str(tmp_path / "logs"),
         str(suite)],
        cwd=suite, env={**os.environ, "PYTHONPATH": str(root)},
        capture_output=True, text=True,
    )
    terminal = result.stdout + result.stderr
    assert result.returncode == 1, terminal
    logs = list((tmp_path / "logs").rglob("test_example.log"))
    assert len(logs) == 1, terminal
    content = logs[0].read_text()
    for message in ("setup output", "call output", "teardown output",
                    "native stderr output", "logged warning", "failed setup output",
                    "intentional failure", "setup broke"):
        assert message in content
    # Native output and log records must not flood the terminal, even with -s.
    assert "native stderr output" not in terminal.splitlines()
    assert "WARNING  root" not in terminal
    assert "test_example.py::test_output FAILED" in terminal
    assert "test_example.py::test_setup_failure ERROR" in terminal
    assert "test_example.py::test_success PASSED" in terminal
    assert "Integration logs:" in terminal
    assert str(logs[0]) in terminal
    assert content.count("--- Captured stdout setup ---") == 2
