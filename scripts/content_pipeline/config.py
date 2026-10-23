"""Registry loading and validation for the content pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

KNOWN_TYPES = ("tutorial", "short", "showcase", "demo")
KNOWN_STATUSES = ("draft", "scripted", "recorded", "published")


class RegistryError(ValueError):
    """Raised when the content registry is invalid."""


@dataclass
class Piece:
    slug: str
    type: str
    title: str
    status: str
    services: list[str] = field(default_factory=list)
    outputs: list[dict[str, str]] = field(default_factory=list)
    redact: dict[str, Any] = field(default_factory=dict)


@dataclass
class Registry:
    defaults: dict[str, Any]
    pieces: list[Piece]

    def piece(self, slug: str) -> Piece:
        for piece in self.pieces:
            if piece.slug == slug:
                return piece
        raise RegistryError(f"Unknown content piece: {slug}")


def load_registry(path: str | Path) -> Registry:
    data = yaml.safe_load(Path(path).read_text())
    if not isinstance(data, dict) or "pieces" not in data:
        raise RegistryError("Registry needs a 'pieces' list.")

    defaults = data.get("defaults") or {}
    pieces: list[Piece] = []
    seen: set[str] = set()
    for raw in data["pieces"]:
        slug = str(raw.get("slug", "")).strip()
        type_ = str(raw.get("type", "")).strip()
        status = str(raw.get("status", "draft")).strip()
        if not slug:
            raise RegistryError("Every piece needs a slug.")
        if slug in seen:
            raise RegistryError(f"Duplicate piece slug: {slug}")
        seen.add(slug)
        if type_ not in KNOWN_TYPES:
            raise RegistryError(
                f"Piece '{slug}' has unknown type '{type_}' "
                f"(known: {', '.join(KNOWN_TYPES)})"
            )
        if status not in KNOWN_STATUSES:
            raise RegistryError(
                f"Piece '{slug}' has unknown status '{status}' "
                f"(known: {', '.join(KNOWN_STATUSES)})"
            )
        pieces.append(
            Piece(
                slug=slug,
                type=type_,
                title=str(raw.get("title", slug)),
                status=status,
                services=[str(s) for s in raw.get("services", [])],
                outputs=list(raw.get("outputs", [])),
                redact=dict(raw.get("redact") or {}),
            )
        )
    return Registry(defaults=defaults, pieces=pieces)
