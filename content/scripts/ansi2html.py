"""Render a truecolor ANSI terminal snapshot (herdr pane read --format ansi) to HTML.

Redaction happens on the cell grid: every replacement keeps the exact length of
the original, so box drawing and column alignment survive and the styling of
each cell is preserved.

    python ansi2html.py in.ansi out.html [--crop r0:r1,c0:c1] [--map redact.json]
"""

from __future__ import annotations

import argparse
import html
import json
import re
import sys
from dataclasses import dataclass, replace
from pathlib import Path

CSI = re.compile(r"\x1b\[([0-9;?]*)([A-Za-z])")
OSC = re.compile(r"\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)")

BASIC = [
    (0, 0, 0), (205, 49, 49), (13, 188, 121), (229, 229, 16),
    (36, 114, 200), (188, 63, 188), (17, 168, 205), (229, 229, 229),
    (102, 102, 102), (241, 76, 76), (35, 209, 139), (245, 245, 67),
    (59, 142, 234), (214, 112, 214), (41, 184, 219), (255, 255, 255),
]


def xterm256(n: int) -> tuple[int, int, int]:
    if n < 16:
        return BASIC[n]
    if n < 232:
        n -= 16
        steps = [0, 95, 135, 175, 215, 255]
        return steps[n // 36], steps[(n // 6) % 6], steps[n % 6]
    v = 8 + (n - 232) * 10
    return v, v, v


@dataclass(frozen=True)
class Style:
    fg: tuple[int, int, int] | None = None
    bg: tuple[int, int, int] | None = None
    bold: bool = False
    dim: bool = False
    italic: bool = False
    underline: bool = False
    reverse: bool = False


def apply_sgr(style: Style, params: str) -> Style:
    codes = [int(p) if p else 0 for p in params.split(";")] if params else [0]
    i = 0
    while i < len(codes):
        c = codes[i]
        if c == 0:
            style = Style()
        elif c == 1:
            style = replace(style, bold=True)
        elif c == 2:
            style = replace(style, dim=True)
        elif c == 3:
            style = replace(style, italic=True)
        elif c == 4:
            style = replace(style, underline=True)
        elif c == 7:
            style = replace(style, reverse=True)
        elif c == 22:
            style = replace(style, bold=False, dim=False)
        elif c == 23:
            style = replace(style, italic=False)
        elif c == 24:
            style = replace(style, underline=False)
        elif c == 27:
            style = replace(style, reverse=False)
        elif c in (38, 48) and i + 1 < len(codes):
            if codes[i + 1] == 2 and i + 4 < len(codes):
                rgb = tuple(codes[i + 2:i + 5])
                i += 4
            elif codes[i + 1] == 5 and i + 2 < len(codes):
                rgb = xterm256(codes[i + 2])
                i += 2
            else:
                rgb = None
            style = replace(style, **{"fg" if c == 38 else "bg": rgb})
        elif c == 39:
            style = replace(style, fg=None)
        elif c == 49:
            style = replace(style, bg=None)
        elif 30 <= c <= 37:
            style = replace(style, fg=BASIC[c - 30])
        elif 90 <= c <= 97:
            style = replace(style, fg=BASIC[c - 90 + 8])
        elif 40 <= c <= 47:
            style = replace(style, bg=BASIC[c - 40])
        elif 100 <= c <= 107:
            style = replace(style, bg=BASIC[c - 100 + 8])
        i += 1
    return style


def parse(text: str) -> list[list[tuple[str, Style]]]:
    text = OSC.sub("", text).replace("\r\n", "\n").replace("\r", "\n")
    rows: list[list[tuple[str, Style]]] = [[]]
    style = Style()
    pos = 0
    for m in CSI.finditer(text + "\x1b[0m"):
        for ch in text[pos:m.start()]:
            if ch == "\n":
                rows.append([])
            elif ch >= " ":
                rows[-1].append((ch, style))
        if m.group(2) == "m":
            style = apply_sgr(style, m.group(1))
        pos = m.end()
    while rows and not rows[-1]:
        rows.pop()
    return rows


GAP = re.compile(r"  +|[│┃║]")


def redact(rows, mapping: dict[str, str]):
    """Replace substrings cell by cell without changing the row length.

    A shorter fake is closed up; the freed cells are re-inserted as spaces at
    the next gap (a run of 2+ spaces or a box border) so later columns and
    borders stay aligned and no stray spaces appear inside a value.
    """
    if any(not old for old in mapping):
        raise ValueError("Redaction originals must not be empty")
    ordered = sorted(mapping.items(), key=lambda kv: -len(kv[0]))
    out = []
    for row in rows:
        cells = list(row)
        for old, new in ordered:
            line = "".join(c for c, _ in cells)
            start = line.find(old)
            while start != -1:
                fake = new[: len(old)]
                styles = [st for _, st in cells[start:start + len(old)]]
                repl = [(ch, styles[min(i, len(styles) - 1)]) for i, ch in enumerate(fake)]
                cells[start:start + len(old)] = repl
                pad = len(old) - len(fake)
                if pad:
                    rest = "".join(c for c, _ in cells)
                    gap = GAP.search(rest, start + len(fake))
                    at = gap.start() if gap else len(cells)
                    fill_style = cells[at][1] if at < len(cells) else styles[-1]
                    cells[at:at] = [(" ", fill_style)] * pad
                line = "".join(c for c, _ in cells)
                start = line.find(old, start + max(1, len(fake)))
        out.append(cells)
    return out


def leftovers(rows, mapping: dict[str, str]) -> list[str]:
    text = "\n".join("".join(c for c, _ in r) for r in rows)
    return sorted({k for k in mapping if k in text})


def css(style: Style, default_fg: str, default_bg: str) -> str:
    fg = "rgb(%d,%d,%d)" % style.fg if style.fg else default_fg
    bg = "rgb(%d,%d,%d)" % style.bg if style.bg else None
    if style.reverse:
        fg, bg = (bg or default_bg), fg
    parts = [f"color:{fg}"]
    if bg:
        parts.append(f"background:{bg}")
    if style.bold:
        parts.append("font-weight:700")
    if style.dim:
        parts.append("opacity:.6")
    if style.italic:
        parts.append("font-style:italic")
    if style.underline:
        parts.append("text-decoration:underline")
    return ";".join(parts)


def to_html(rows, *, default_fg="#d8dee9", default_bg="#121212", width=None) -> str:
    width = width or max((len(r) for r in rows), default=0)
    lines = []
    for row in rows:
        row = row + [(" ", Style())] * (width - len(row))
        spans, buf, cur = [], [], None
        for ch, st in row:
            if st != cur and buf:
                spans.append(f'<span style="{css(cur, default_fg, default_bg)}">{html.escape("".join(buf))}</span>')
                buf = []
            cur = st
            buf.append(ch)
        if buf:
            spans.append(f'<span style="{css(cur, default_fg, default_bg)}">{html.escape("".join(buf))}</span>')
        lines.append("".join(spans))
    return "\n".join(lines)


def keep_rows(rows, spec: str | None):
    """Keep only the listed row ranges, e.g. "0:1,4:27"."""
    if not spec:
        return rows
    kept = []
    for part in spec.split(","):
        a, b = (int(x) if x else None for x in part.split(":"))
        kept.extend(rows[a:b])
    return kept


def fit(rows, width: int | None):
    """Narrow a terminal capture to `width` without visibly cutting it.

    Rich panels are redrawn with their right border at the new edge (titles
    re-centred); text that no longer fits ends in an ellipsis.
    """
    if not width:
        return rows
    out = []
    for row in rows:
        if len(row) <= width:
            out.append(row)
            continue
        text = "".join(c for c, _ in row)
        left = len(text) - len(text.lstrip(" "))
        lead = text[left:left + 1]
        right = text.rstrip(" ")
        tail = right[-1:] if right else ""
        last = len(right) - 1
        if lead == "╭" and tail == "╮":
            border = row[left][1]
            title_cells = [(c, s) for c, s in row[left + 1:last] if c != "─"]
            while title_cells and title_cells[0][0] == " ":
                title_cells.pop(0)
            while title_cells and title_cells[-1][0] == " ":
                title_cells.pop()
            inner = width - left - 2
            title = ([(" ", border)] + title_cells + [(" ", border)]) if title_cells else []
            title = title[:inner]
            pad = inner - len(title)
            new = row[:left] + [("╭", border)] + [("─", border)] * (pad // 2) + title \
                + [("─", border)] * (pad - pad // 2) + [("╮", border)]
        elif lead == "╰" and tail == "╯":
            border = row[left][1]
            new = row[:left] + [("╰", border)] + [("─", border)] * (width - left - 2) + [("╯", border)]
        elif lead == "│" and tail == "│":
            border = row[last][1]
            body = row[:width - 1]
            cut = "".join(c for c, _ in row[width - 2:last]).strip()
            if cut:
                body = body[:-2] + [("…", body[-2][1]), (" ", body[-1][1])]
            new = body + [("│", border)]
        else:
            new = row[:width]
            if "".join(c for c, _ in row[width - 1:]).strip():
                new = new[:-1] + [("…", new[-1][1])]
        out.append(new)
    return out


def crop(rows, spec: str | None):
    if not spec:
        return rows
    r, c = spec.split(",")
    r0, r1 = (int(x) if x else None for x in r.split(":"))
    c0, c1 = (int(x) if x else None for x in c.split(":"))
    return [row[c0:c1] for row in rows[r0:r1]]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("src")
    ap.add_argument("out")
    ap.add_argument("--crop")
    ap.add_argument("--map", help="JSON {original: replacement}")
    ap.add_argument("--rows", help="row ranges to keep before cropping, e.g. 0:1,4:27")
    ap.add_argument("--fit", type=int, help="narrow to this width, redrawing panel borders")
    a = ap.parse_args()
    rows = parse(Path(a.src).read_text(encoding="utf-8", errors="replace"))
    mapping = json.loads(Path(a.map).read_text()) if a.map else {}
    rows = redact(rows, mapping)
    left = leftovers(rows, mapping)
    if left:
        print("LEAK after redaction:", left, file=sys.stderr)
        return 1
    rows = fit(crop(keep_rows(rows, a.rows), a.crop), a.fit)
    Path(a.out).write_text(to_html(rows), encoding="utf-8")
    print(f"{a.out}: {len(rows)} rows x {max((len(r) for r in rows), default=0)} cols")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
