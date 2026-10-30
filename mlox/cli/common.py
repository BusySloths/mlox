from __future__ import annotations

from typing import Dict, List
import json
import re
from collections.abc import Mapping
from pathlib import Path

import typer

from mlox.application.result import OperationResult


def _json_value(value):
    """Convert result payloads without exposing fields of live domain objects."""
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, Mapping):
        return {
            str(key): ("[redacted]" if not str(key).endswith("_uuid") and re.search(
                r"password|passwd|secret|token|private.?key|api.?key", str(key), re.I
            ) else _json_value(item))
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple, set)):
        return [_json_value(item) for item in value]
    fields = ("uuid", "name", "state", "ip", "port", "service_urls", "service_ports")
    return {key: _json_value(getattr(value, key)) for key in fields if hasattr(value, key)}


def json_output() -> bool:
    ctx = typer.get_current_context(silent=True) if hasattr(typer, "get_current_context") else None
    if ctx is None:
        import click
        ctx = click.get_current_context(silent=True)
    return bool(ctx and ctx.find_root().obj and ctx.find_root().obj.get("output") == "json")


def handle_result(result: OperationResult) -> OperationResult:
    """Raise a ``typer.Exit`` when an operation fails."""

    if json_output():
        typer.echo(json.dumps({"success": result.success, "code": result.code,
                               "message": result.message, "data": _json_value(result.data),
                               "error": None if result.success else "operation_failed"}, allow_nan=False))
        raise typer.Exit(code=0 if result.success else result.code or 1)
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
