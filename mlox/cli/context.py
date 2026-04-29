from __future__ import annotations

import os
from typing import Optional, Tuple

import typer

PROJECT_ENVVAR = "MLOX_PROJECT_NAME"
PASSWORD_ENVVAR = "MLOX_PROJECT_PASSWORD"


def resolve_project(raw: Optional[str]) -> str:
    if raw:
        return raw
    env_value = os.getenv(PROJECT_ENVVAR)
    if env_value:
        return env_value
    raise typer.BadParameter(
        f"Provide a project name or set {PROJECT_ENVVAR}.",
        param_hint="project",
    )


def resolve_password(
    raw: Optional[str],
    prompt_text: str = "Password for the session",
) -> str:
    if raw:
        return raw
    env_value = os.getenv(PASSWORD_ENVVAR)
    if env_value:
        return env_value
    return typer.prompt(prompt_text, hide_input=True)


def resolve_credentials(
    project: Optional[str],
    password: Optional[str],
    prompt_text: str = "Password for the session",
) -> Tuple[str, str]:
    return resolve_project(project), resolve_password(password, prompt_text)
