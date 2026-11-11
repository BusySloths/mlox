"""Render a reviewed selection of ANSI frames into deck HTML fragments."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from scripts.content_pipeline import ansi2html


def build(manifest: Path, frames: Path, out: Path, mapping: Path) -> list[Path]:
    replacements = json.loads(mapping.read_text(encoding="utf-8"))
    if not isinstance(replacements, dict) or any(
        not isinstance(k, str) or not k or not isinstance(v, str)
        for k, v in replacements.items()
    ):
        raise ValueError("Redaction map must contain nonempty original strings and string replacements")
    selections = json.loads(manifest.read_text(encoding="utf-8"))
    rendered = []
    for name, spec in selections.items():
        if Path(name).name != name or name in {"", ".", ".."}:
            raise ValueError("Capture names must be plain filenames")
        source = (frames / spec["frame"]).resolve()
        if not source.is_relative_to(frames.resolve()):
            raise ValueError("Frame must be inside the frames directory")
        rows = ansi2html.parse(source.read_text(encoding="utf-8", errors="replace"))
        rows = ansi2html.redact(rows, replacements)
        if ansi2html.leftovers(rows, replacements):
            raise ValueError(f"Original text remains in capture {name}")
        rows = ansi2html.fit(
            ansi2html.crop(ansi2html.keep_rows(rows, spec.get("rows")), spec.get("crop")),
            spec.get("fit"),
        )
        rendered.append((out / f"{name}.html", ansi2html.to_html(rows)))
    out.mkdir(parents=True, exist_ok=True)
    for path, html in rendered:
        path.write_text(html, encoding="utf-8")
    return [path for path, _ in rendered]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--frames", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--map", type=Path, required=True, dest="mapping")
    args = parser.parse_args(argv)
    for path in build(args.manifest, args.frames, args.out, args.mapping):
        print(f"wrote {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
