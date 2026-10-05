"""Persisted project-level operations activity records."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class OperationsEvent:
    """One immutable event in the project's operations audit trail."""

    event_type: str
    summary: str
    actor: str = "system"
    target: str = ""
    status: str = "recorded"
    details: dict[str, Any] = field(default_factory=dict)
    id: str = ""
    created_at: str = ""
