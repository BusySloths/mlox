#!/usr/bin/env python3
"""Generate the authoritative service/server catalog from YAML plugin configs.

Facts about bundled services and servers live in the YAML configs under
``mlox/services/**/mlox*.yaml`` and ``mlox/servers/**/mlox-server*.yaml``.
This script regenerates the human-facing catalog Markdown from those files so
that README/website/wiki never restate the catalog by hand.

Outputs (both are derived artifacts, committed and kept in sync by
``scripts/check_docs.py`` in CI):

- ``docs/SERVICES_CATALOG.md``  (primary, linked from README and website)
- ``wiki/Services-Catalog.md``  (surfaced to the GitHub wiki at deploy time)

Usage:

    python scripts/generate_service_catalog.py
"""

from __future__ import annotations

import argparse
import glob
import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUTPUTS = [
    str(REPO_ROOT / "docs" / "SERVICES_CATALOG.md"),
    str(REPO_ROOT / "wiki" / "Services-Catalog.md"),
]


@dataclass
class CatalogEntry:
    id: str
    name: str
    version: str
    description: str
    backends: list[str] = field(default_factory=list)
    capabilities: list[str] = field(default_factory=list)
    config: str = field(default="")


def _as_list(value) -> list[str]:
    """Normalize a dict/list/scalar into a sorted list of key names."""
    if value is None:
        return []
    if isinstance(value, dict):
        return sorted(str(k) for k in value.keys())
    if isinstance(value, (list, tuple, set)):
        return sorted(str(v) for v in value)
    return [str(value)]


def _parse(data: dict, config_rel: str) -> CatalogEntry:
    capabilities = data.get("capabilities") or {}
    groups = data.get("groups") or {}
    backends = _as_list(capabilities.get("backend")) or _as_list(
        groups.get("backend")
    )
    service_caps = _as_list(capabilities.get("service"))
    server_caps = _as_list(capabilities.get("server"))
    if not service_caps:
        service_caps = _as_list(groups.get("service"))
    return CatalogEntry(
        id=str(data.get("id", "")),
        name=str(data.get("name", "")),
        version=str(data.get("version", "")),
        description=(data.get("description_short") or data.get("description") or "")
        .strip()
        .replace("\n", " "),
        backends=backends,
        capabilities=sorted(set(service_caps + server_caps)),
        config=config_rel,
    )


def _collect(glob_pattern: str) -> list[CatalogEntry]:
    entries: list[CatalogEntry] = []
    for path in sorted(glob.glob(str(REPO_ROOT / glob_pattern))):
        rel = os.path.relpath(path, REPO_ROOT).replace(os.sep, "/")
        with open(path, "r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh)
        if not isinstance(data, dict):
            continue
        entry = _parse(data, rel)
        if entry.name:
            entries.append(entry)
    # Sort by name, then version, so the table is stable and diffable.
    return sorted(entries, key=lambda e: (e.name.lower(), e.version))


def _render_table(entries: list[CatalogEntry]) -> str:
    rows = [
        "| Service | Version | Backends | Description |",
        "|---------|---------|----------|-------------|",
    ]
    for e in entries:
        backends = ", ".join(e.backends) or "—"
        description = e.description or "—"
        rows.append(
            f"| **{e.name}** | {e.version} | {backends} | {description} |"
        )
    return "\n".join(rows)


def _render(services: list[CatalogEntry], servers: list[CatalogEntry]) -> str:
    lines: list[str] = []
    lines.append("# Services Catalog")
    lines.append(
        "\n> AUTO-GENERATED. Do not edit by hand. Run "
        "`python scripts/generate_service_catalog.py` to regenerate from the "
        "YAML configs. Any hand-written catalog content is a drift bug."
    )
    lines.append(
        "\nThe authoritative, exhaustive list of services and servers bundled "
        "with MLOX. Generated from the YAML plugin configs; the single source "
        "of truth is those configs, not this page."
    )

    lines.append(f"\n**{len(services)} service configs, "
                 f"{len(servers)} server configs.**")

    lines.append("\n---\n\n## Contents")
    lines.append("")
    lines.append("1. [Services](#services)")
    lines.append("2. [Servers](#servers)")

    lines.append("\n---\n\n## Services")
    lines.append("")
    lines.append(_render_table(services))

    lines.append("\n---\n\n## Servers")
    lines.append("")
    lines.append(_render_table(servers))

    lines.append("\n---\n\n## Status Legend")
    lines.append("")
    lines.append(
        "Maturity/status (Functional, Beta, Experimental) is not part of the "
        "YAML schema and is therefore NOT listed here. It is tracked in "
        "`docs/DOCTRINE.md` — the single point of truth for status."
    )
    lines.append("")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--outputs",
        nargs="*",
        default=DEFAULT_OUTPUTS,
        help="Markdown files to write (default: docs + wiki catalog).",
    )
    args = parser.parse_args()

    services = _collect("mlox/services/**/mlox*.yaml")
    servers = _collect("mlox/servers/**/mlox-server*.yaml")
    rendered = _render(services, servers)

    for output in args.outputs:
        out_path = Path(output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(rendered + "\n", encoding="utf-8")
        print(f"Wrote {out_path} ({len(services)} services, {len(servers)} servers)")


if __name__ == "__main__":
    main()
