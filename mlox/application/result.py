from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class OperationResult:
    """Container describing the outcome of an operation."""

    success: bool
    code: int
    message: str
    data: Any | None = None

    def __bool__(self) -> bool:  # pragma: no cover - syntactic sugar
        return self.success
