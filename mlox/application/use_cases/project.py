from __future__ import annotations

from mlox.application.result import OperationResult


def create_project(load_session, name: str, password: str) -> OperationResult:
    result = load_session(name, password, refresh=True)
    if not result.success:
        return result

    return OperationResult(
        True,
        0,
        f"Created project '{name}'.",
        {"session": result.data},
    )
