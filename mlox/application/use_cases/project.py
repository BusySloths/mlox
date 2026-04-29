from __future__ import annotations

from mlox.application.result import OperationResult


def create_project(session, name: str) -> OperationResult:
    return OperationResult(
        True,
        0,
        f"Created project '{name}'.",
        {"session": session},
    )
