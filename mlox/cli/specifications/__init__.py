"""Declarative CLI contracts grouped by workspace domain."""

from mlox.cli.specifications.model import MODEL_COMMANDS
from mlox.cli.specifications.server import SERVER_COMMANDS, SERVER_CONFIG_COMMANDS
from mlox.cli.specifications.service import (
    SERVICE_COMMANDS,
    SERVICE_CONFIG_COMMANDS,
)

__all__ = [
    "MODEL_COMMANDS",
    "SERVER_COMMANDS",
    "SERVER_CONFIG_COMMANDS",
    "SERVICE_COMMANDS",
    "SERVICE_CONFIG_COMMANDS",
]
