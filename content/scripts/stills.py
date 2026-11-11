"""Render redacted HTML captures to PNG/WebP stills and GIFs with headless Chrome.

The manifest names captures (from the ``captures`` stage) and where each output
goes. All frames of one GIF share a grid size; shorter captures are padded.

    {
      "png": [{"capture": "overview", "dest": "website/public/x.png", "width": 1920, "webp": true}],
      "gif": [{"dest": "mlox/resources/x.gif", "width": 960, "cols": 174, "rows": 61,
               "frames": [{"capture": "login", "hold": 2.0}]}]
    }
"""

from __future__ import annotations

import argparse
import html
import json
import math
import re
import subprocess
import tempfile
from pathlib import Path

from PIL import Image

CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
FONT_DIR = Path("website/src/assets/fonts")
PAD_X, PAD_Y = 12, 10  # px around the text, as on the website
ADVANCE, LINE = 0.6, 1.24  # JetBrains Mono advance and the capture line height
BACKGROUND = "#121212"


def grid(fragment: str) -> tuple[int, int]:
    """Columns and rows of a capture fragment."""
    lines = html.unescape(re.sub(r"<[^>]+>", "", fragment)).split("\n")
    return max((len(line) for line in lines), default=0), len(lines)


def page(fragment: str, cols: int, rows: int, font_size: float, font_dir: Path) -> str:
    fonts = "".join(
        f'@font-face{{font-family:JBM;src:url("{(font_dir / f"JetBrainsMono-{name}.woff2").resolve().as_uri()}")'
        f' format("woff2");font-weight:{weight}}}'
        for name, weight in (("Regular", 400), ("Bold", 700))
    )
    return (
        f'<!doctype html><meta charset="utf-8"><style>{fonts}'
        f"html,body{{margin:0;background:{BACKGROUND};overflow:hidden}}"
        f"pre{{margin:0;padding:{PAD_Y}px {PAD_X}px;font:{font_size}px/{LINE} JBM,monospace;color:#d8dee9;"
        f"width:{cols * ADVANCE}em;height:{rows * LINE}em;white-space:pre;font-variant-ligatures:none}}"
        f"</style><pre>{fragment}</pre>"
    )


def size(cols: int, rows: int, width: int) -> tuple[float, int]:
    """Font size that fits `cols` into `width` CSS px, and the resulting height."""
    font_size = (width - 2 * PAD_X) / (cols * ADVANCE)
    return font_size, math.ceil(rows * LINE * font_size + 2 * PAD_Y)


def screenshot(fragment: str, out: Path, *, width: int, cols: int | None = None, rows: int | None = None,
               scale: int = 2, font_dir: Path = FONT_DIR, chrome: str = CHROME) -> Path:
    """Render one capture at `width` x `scale` device pixels."""
    own_cols, own_rows = grid(fragment)
    cols, rows = cols or own_cols, rows or own_rows
    font_size, height = size(cols, rows, width)
    out.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        src = Path(tmp) / "page.html"
        src.write_text(page(fragment, cols, rows, font_size, font_dir), encoding="utf-8")
        subprocess.run(
            [chrome, "--headless=new", "--disable-gpu", "--hide-scrollbars",
             f"--force-device-scale-factor={scale}", f"--window-size={width},{height}",
             f"--screenshot={out.resolve()}", src.as_uri()],
            check=True, capture_output=True,
        )
    return out


def gif(frames: list[tuple[Path, float]], out: Path, *, width: int) -> Path:
    """Assemble stills into a looping GIF; each frame is held for its own seconds."""
    images = []
    for path, _ in frames:
        with Image.open(path) as image:
            image = image.convert("RGB")
            height = round(image.height * width / image.width)
            images.append(image.resize((width, height), Image.LANCZOS).quantize(colors=256))
    out.parent.mkdir(parents=True, exist_ok=True)
    images[0].save(out, save_all=True, append_images=images[1:], loop=0, optimize=True,
                   duration=[round(hold * 1000) for _, hold in frames], disposal=1)
    return out


def build(manifest: Path, captures: Path, work: Path, root: Path = Path(".")) -> list[Path]:
    spec = json.loads(manifest.read_text(encoding="utf-8"))
    fragment = lambda name: (captures / f"{name}.html").read_text(encoding="utf-8")  # noqa: E731
    written = []
    for item in spec.get("png", []):
        out = root / item["dest"]
        tmp = screenshot(fragment(item["capture"]), work / f"{item['capture']}@{item['width']}.png",
                         width=item["width"], scale=2)
        with Image.open(tmp) as image:
            image = image.convert("RGB")
            image = image.resize((item["width"], round(image.height / 2)), Image.LANCZOS)
            out.parent.mkdir(parents=True, exist_ok=True)
            image.save(out, optimize=True)
            written.append(out)
            if item.get("webp"):
                image.save(out.with_suffix(".webp"), quality=90, method=6)
                written.append(out.with_suffix(".webp"))
    for item in spec.get("gif", []):
        stills = [
            (screenshot(fragment(f["capture"]), work / "gif" / f"{f['capture']}.png",
                        width=item["width"], cols=item["cols"], rows=item["rows"]), f["hold"])
            for f in item["frames"]
        ]
        written.append(gif(stills, root / item["dest"], width=item["width"]))
    return written


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--captures", type=Path, required=True)
    parser.add_argument("--work", type=Path, required=True, help="directory for intermediate stills")
    args = parser.parse_args(argv)
    for path in build(args.manifest, args.captures, args.work):
        print(f"wrote {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
