"""Declarative CLI contract for model workspace operations."""

from __future__ import annotations

from mlox.cli.generation import CliParameter, WorkspaceCommand
from mlox.cli.rendering.results import render_models


MODEL_COMMANDS = (
    WorkspaceCommand(
        name="list",
        method="list_models",
        help="List registered models from the configured MLflow registry.",
        parameters=(
            CliParameter(
                "registry",
                "Name or ID of the model registry service to use.",
                target="registry_name",
                declarations=("--registry", "-r"),
            ),
        ),
        renderer=render_models,
    ),
)
