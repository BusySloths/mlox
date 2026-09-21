from __future__ import annotations

from dataclasses import dataclass
from typing import Generic, TypeVar


T = TypeVar("T")


@dataclass
class OperationResult(Generic[T]):
    """Container describing an operation outcome and its typed payload."""

    success: bool
    code: int
    message: str
    data: T | None = None

    def __bool__(self) -> bool:  # pragma: no cover - syntactic sugar
        return self.success
