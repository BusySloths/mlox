"""Build the operator demo deck: inline redacted captures, then print to PDF.

    uv run python content/operator-demo/deck/build.py [--pdf OUT.pdf]

`deck.html` references captures as `{{capture:<name>}}`; each name resolves to
`captures/<name>.html`, a redacted HTML rendering of a terminal snapshot. A
missing capture renders as a visible "pending" placeholder, so the deck can be
reviewed before every stage of the demo has been recorded.

The PDF goes to content/.work/operator-demo/ (outside git) unless --pdf is given.
"""

from __future__ import annotations

import argparse
import re
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
SLOT = re.compile(r"\{\{capture:([\w-]+)\}\}")


def inline_captures(template: str) -> tuple[str, list[str]]:
    missing: list[str] = []

    def fill(match: re.Match) -> str:
        path = HERE / "captures" / f"{match.group(1)}.html"
        if path.exists():
            return path.read_text(encoding="utf-8")
        missing.append(match.group(1))
        return f'<span class="pending">capture pending · {match.group(1)}</span>'

    return SLOT.sub(fill, template), missing


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pdf", type=Path, default=REPO / "content/.work/operator-demo/operator-demo-deck.pdf")
    ap.add_argument("--html-only", action="store_true")
    args = ap.parse_args()

    html, missing = inline_captures((HERE / "deck.html").read_text(encoding="utf-8"))
    out_dir = args.pdf.parent
    out_dir.mkdir(parents=True, exist_ok=True)
    built = out_dir / "deck.built.html"
    html = html.replace('href="deck.css"', f'href="{HERE / "deck.css"}"').replace("{{repo}}", str(REPO))
    built.write_text(html, encoding="utf-8")
    if missing:
        print("pending captures:", ", ".join(missing))
    if args.html_only:
        print(built)
        return 0
    subprocess.run(
        [CHROME, "--headless=new", "--disable-gpu", "--no-pdf-header-footer",
         "--virtual-time-budget=8000", f"--print-to-pdf={args.pdf}", built.as_uri()],
        check=True, capture_output=True,
    )
    print(args.pdf)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
