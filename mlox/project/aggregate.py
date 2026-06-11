"""Domain aggregate for an MLOX project."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict

from mlox.infra import Infrastructure


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class ProjectAggregate:
    """Project metadata and its infrastructure graph."""

    name: str
    id: str = ""
    descr: str = ""
    version: str = "1"
    created_at: str = field(default_factory=_now)
    last_opened_at: str = field(default_factory=_now)
    data_source_id: str = ""
    data_source_kind: str = "sqlcipher"
    data_source_location: str = "self"
    data_source_config: Dict[str, Any] = field(default_factory=dict)
    infrastructure: Infrastructure = field(default_factory=Infrastructure)

    def touch(self) -> None:
        self.last_opened_at = _now()
