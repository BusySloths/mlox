from __future__ import annotations

from typing import Dict, List

import typer

from mlox.application.result import OperationResult


def handle_result(result: OperationResult) -> OperationResult:
    """Raise a ``typer.Exit`` when an operation fails."""

    if not result.success:
        typer.echo(f"[ERROR] {result.message}", err=True)
        raise typer.Exit(code=result.code)
    return result


def parse_kv(pairs: List[str]) -> Dict[str, str]:
    """Convert a list of ``KEY=VALUE`` strings into a dictionary."""

    data: Dict[str, str] = {}
    for item in pairs:
        if "=" not in item:
            continue
        key, value = item.split("=", 1)
        data[key] = value
    return data
