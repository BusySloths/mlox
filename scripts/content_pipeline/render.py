"""Render stage: script.md → article markdown for the docs surface."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

FRONT_MATTER_RE = re.compile(r"^---\n(.*?)\n---\n", re.DOTALL)


@dataclass
class Script:
    front_matter: dict
    body: str


def parse_script(path: str | Path) -> Script:
    text = Path(path).read_text()
    match = FRONT_MATTER_RE.match(text)
    meta: dict = {}
    if match:
        import yaml

        meta = yaml.safe_load(match.group(1)) or {}
        text = text[match.end():]
    return Script(front_matter=meta, body=text.strip())


def render_article(script_path: str | Path, timeline: dict | None = None) -> str:
    """Render the canonical docs article from the tutorial script."""
    script = parse_script(script_path)
    meta = script.front_matter
    title = meta.get("title", "Untitled")
    out = [f"# {title}", ""]
    if timeline:
        out.append("## Chapters")
        out.append("")
        for chapter in timeline.get("chapters", []):
            label = chapter.get("label") or chapter.get("name", "")
            start = chapter.get("start", "")
            out.append(f"- `{start}` {label}")
        out.append("")
    out.append(script.body)
    return "\n".join(out).strip() + "\n"


def publish_article(script_path: str | Path, dest: str | Path) -> Path:
    article = render_article(script_path)
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(article)
    return dest
