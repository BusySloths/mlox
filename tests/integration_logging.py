"""Opt-in quiet integration runs with complete pytest capture per module."""

from datetime import datetime
from pathlib import Path
import tempfile

import pytest


def pytest_addoption(parser):
    group = parser.getgroup("integration logging")
    group.addoption(
        "--integration-quiet", action="store_true",
        help="Capture integration output in per-module files under the system temp directory.",
    )
    group.addoption(
        "--integration-log-dir", metavar="PATH",
        help="Parent directory for a new integration log directory; also enables quiet mode.",
    )


def pytest_configure(config):
    parent = config.getoption("--integration-log-dir")
    if not (config.getoption("--integration-quiet") or parent):
        return
    # Override the repository's -s and live logging defaults before capture starts.
    config.option.capture = "fd"
    capture = config.pluginmanager.getplugin("capturemanager")
    if capture is not None and capture._method != "fd":
        # Capture is initialized before conftest's configure hook. Restart it
        # with fd capture so the repository's earlier -s is actually overridden.
        capture.stop_global_capturing()
        capture._method = "fd"
        capture.start_global_capturing()
        capture.suspend_global_capture()
    # Keep pytest's test names and outcomes visible despite the default -q.
    config.option.verbose = max(1, config.option.verbose)
    config.option.showcapture = "no"
    config.option.log_cli_level = "CRITICAL"
    config.inicfg["log_cli"] = False
    if config.option.log_level is None:
        config.option.log_level = "INFO"
    if parent:
        Path(parent).expanduser().mkdir(parents=True, exist_ok=True)
        parent = str(Path(parent).expanduser())
    directory = Path(tempfile.mkdtemp(
        prefix=datetime.now().strftime("mlox-integration-%Y%m%d-%H%M%S-"), dir=parent,
    ))
    config.pluginmanager.register(ModuleLogs(directory), "integration-module-logs")


class ModuleLogs:
    def __init__(self, directory):
        self.directory = directory
        self.paths = {}

    @pytest.fixture(scope="session", autouse=True)
    def noninteractive_fabric(self):
        # Invoke otherwise forwards pytest's unreadable captured stdin into SSH
        # commands, including ServerConnection's initial `true` probe.
        from fabric import Connection
        from functools import wraps

        original_init = Connection.__init__

        @wraps(original_init)
        def initialize(connection, *args, **kwargs):
            original_init(connection, *args, **kwargs)
            connection.config.run.in_stream = False

        with pytest.MonkeyPatch.context() as patch:
            patch.setattr(Connection, "__init__", initialize)
            yield

    def pytest_report_header(self):
        return f"Integration logs: {self.directory}"

    @pytest.hookimpl(hookwrapper=True)
    def pytest_runtest_makereport(self, item, call):
        outcome = yield
        report = outcome.get_result()
        if item.get_closest_marker("integration") is None:
            return
        module = report.nodeid.split("::", 1)[0]
        if module not in self.paths:
            # Preserve the module path so equal basenames cannot collide.
            relative = Path(*[part for part in Path(module).parts if part not in {"/", ".."}])
            path = self.directory / relative.with_suffix(".log")
            path.parent.mkdir(parents=True, exist_ok=True)
            self.paths[module] = path
        with self.paths[module].open("a", encoding="utf-8") as stream:
            stream.write(f"\n=== {report.nodeid} [{report.when}: {report.outcome}] ===\n")
            for title, content in report.sections:
                # Call/teardown reports also contain earlier phases' captures.
                if title.endswith(f" {report.when}"):
                    stream.write(f"\n--- {title} ---\n{content}\n")
            if report.longrepr:
                stream.write(f"\n{report.longreprtext}\n")

    def pytest_terminal_summary(self, terminalreporter):
        terminalreporter.write_sep("-", f"Integration logs: {self.directory}")
        for module, path in sorted(self.paths.items()):
            terminalreporter.write_line(f"{module}: {path}")
