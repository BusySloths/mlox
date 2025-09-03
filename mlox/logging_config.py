import os
import sys
import logging
import logging.config

from typing import Optional

# Try to use colorama on platforms that need it (optional dependency)
try:
    import colorama  # type: ignore

    colorama.init(autoreset=True)
    _HAS_COLORAMA = True
except Exception:
    _HAS_COLORAMA = False

LOG_FORMAT = "%(asctime)s | %(levelname_colored)s | %(module)s.%(funcName)s:%(lineno)d | %(message)s"
DATE_FMT = "%Y-%m-%d %H:%M:%S"

# ANSI color codes
_COLORS = {
    "DEBUG": "\033[36m",  # cyan
    "INFO": "\033[32m",  # green
    "WARNING": "\033[33m",  # yellow
    "ERROR": "\033[31m",  # red
    "CRITICAL": "\033[35m",  # magenta
}
_RESET = "\033[0m"


class ColoredFormatter(logging.Formatter):
    def __init__(self, fmt: str, datefmt: Optional[str] = None, use_color: bool = True):
        super().__init__(fmt, datefmt=datefmt)
        # If output is not a tty or NO_COLOR set, disable colors
        if not use_color or os.getenv("NO_COLOR"):
            self.use_color = False
        else:
            self.use_color = sys.stdout.isatty() or _HAS_COLORAMA

    def format(self, record: logging.LogRecord) -> str:
        levelname = record.levelname
        if self.use_color and levelname in _COLORS:
            record.levelname_colored = f"{_COLORS[levelname]}{levelname}{_RESET}"
        else:
            record.levelname_colored = levelname
        return super().format(record)


LOG_CONFIG = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "colored": {
            "()": ColoredFormatter,
            "fmt": LOG_FORMAT,
            "datefmt": DATE_FMT,
            "use_color": True,
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "colored",
            "level": "INFO",
            "stream": "ext://sys.stdout",
        }
    },
    "root": {"handlers": ["console"], "level": "INFO"},
}


def configure_logging() -> None:
    """Configure logging for the project. Call once at startup.
    Set NO_COLOR=1 to disable colors, or install colorama for Windows support.
    """
    logging.config.dictConfig(LOG_CONFIG)
