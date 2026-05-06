"""Live application log drawer."""

from __future__ import annotations

import logging

from textual.app import ComposeResult
from textual.containers import Container

try:
    from textual.widgets import Log as LogWidget
except ImportError:  # pragma: no cover - fallback for older textual releases
    from textual.widgets import TextLog as LogWidget  # type: ignore


LOG_FORMAT = (
    "%(asctime)s | %(levelname)s | "
    "%(module)s.%(funcName)s:%(lineno)d | %(message)s"
)
DATE_FMT = "%Y-%m-%d %H:%M:%S"


class TextualLogHandler(logging.Handler):
    """Logging handler that appends records to a mounted Textual log widget."""

    def __init__(self, panel: "AppLogPanel") -> None:
        super().__init__(level=logging.INFO)
        self.panel = panel
        self.setFormatter(logging.Formatter(LOG_FORMAT, datefmt=DATE_FMT))

    def emit(self, record: logging.LogRecord) -> None:
        try:
            line = self.format(record)
        except Exception:
            self.handleError(record)
            return

        app = getattr(self.panel, "app", None)
        if app and app.is_running:
            try:
                app.call_from_thread(self.panel.write_line, line)
            except RuntimeError:
                self.panel.write_line(line)
        else:
            self.panel.write_line(line)


class AppLogPanel(Container):
    """Live view of Python logging records emitted by the application."""

    def __init__(self, *children, max_lines: int = 500, **kwargs) -> None:
        super().__init__(*children, **kwargs)
        self.max_lines = max_lines
        self._handler: TextualLogHandler | None = None
        self._lines: list[str] = []

    def compose(self) -> ComposeResult:
        yield LogWidget(id="app-log-output", highlight=True)

    @property
    def log_output(self) -> LogWidget:
        return self.query_one("#app-log-output", LogWidget)

    def on_mount(self) -> None:
        self._handler = TextualLogHandler(self)
        logging.getLogger().addHandler(self._handler)
        self.write_line("Live application logging attached.")

    def on_unmount(self) -> None:
        if self._handler:
            logging.getLogger().removeHandler(self._handler)
            self._handler.close()
            self._handler = None

    def write_line(self, line: str) -> None:
        self._lines.append(line)
        if len(self._lines) > self.max_lines:
            self._lines = self._lines[-self.max_lines :]
            self.log_output.clear()
            for cached_line in self._lines:
                self.log_output.write_line(cached_line)
            return
        self.log_output.write_line(line)
