"""Redact stage: detect sensitive entities in a recording, build a reviewed
replacement mapping, apply scene-windowed in-place text replacement, and
verify artifacts for leaks.

Detection is a candidate generator (tesseract TSV, local and free); the
redaction.json mapping is reviewed in-flow before anything is rendered, and
`verify` re-scans final artifacts against the original entities before
publish.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
from collections import Counter
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from pathlib import Path
from typing import TYPE_CHECKING, Callable

if TYPE_CHECKING:
    import numpy as np

IP_RE = re.compile(r"^([^\w]*)(\d{1,3}(?:\.\d{1,3}){3})([^\w]*)$")
DEFAULT_MAX_FS = 14
DEFAULT_MIN_FS = 10
DEFAULT_CHAR_W = 0.62
DEFAULT_IP_PREFIX = "198.51.100"
DEFAULT_LITERALS = {
    "nicococo": "demo",
    "ooitflow": "demoflow",
    "tootflow": "demoflow",
}
DEFAULT_PREFIXES = {
    "airtime-event": "demo-event-recommender",
    "airtime-recom": "demo-recommender",
    "airtime-ml": "demo-ml",
}
DEFAULT_FONT = "/usr/share/fonts/TTF/JetBrainsMonoNerdFont-Regular.ttf"
# First existing file wins; MLOX_CONTENT_FONT overrides. Menlo ships with macOS.
FONT_CANDIDATES = (
    DEFAULT_FONT,
    str(Path.home() / "Library/Fonts/JetBrainsMonoNerdFont-Regular.ttf"),
    "/Library/Fonts/JetBrainsMonoNerdFont-Regular.ttf",
    "/System/Library/Fonts/Menlo.ttc",
    "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
)


def default_font() -> str:
    """Return the replacement-text font for this machine."""
    override = os.environ.get("MLOX_CONTENT_FONT")
    if override:
        return override
    for candidate in FONT_CANDIDATES:
        if Path(candidate).exists():
            return candidate
    raise FileNotFoundError(
        "No monospace font found for redaction text; set MLOX_CONTENT_FONT.")


def _drawtext_literal(text: str) -> str:
    """Quote text for a drawtext option inside an ffmpeg filtergraph.

    The graph parser strips the outer quotes, so backslash and ':' are escaped
    for the option parser. A quote cannot survive both levels; use U+2019.
    """
    escaped = text.replace("\\", "\\\\").replace(":", "\\:")
    return "'" + escaped.replace("'", "’") + "'"


# .10, .20 … .240 first (obviously made up), then the remaining valid octets
_FAKE_OCTETS = [o for o in range(10, 250, 10)] + [o for o in range(1, 255) if o % 10]


def fake_ip(addr: str, prefix: str, ip_map: dict[str, str]) -> str:
    """Stable fake for `addr` within `ip_map`, never reusing its real last octet."""
    if addr not in ip_map:
        real_last = int(addr.rsplit(".", 1)[1])
        start = len(ip_map) % len(_FAKE_OCTETS)
        for k in range(len(_FAKE_OCTETS)):
            octet = _FAKE_OCTETS[(start + k) % len(_FAKE_OCTETS)]
            if octet != real_last:
                break
        ip_map[addr] = f"{prefix}.{octet}"
    return ip_map[addr]


def classify_word(
    word: str,
    *,
    literals: dict[str, str] | None = None,
    prefixes: dict[str, str] | None = None,
    ip_prefix: str = DEFAULT_IP_PREFIX,
    ip_map: dict[str, str] | None = None,
) -> str | None:
    """Replacement for one OCR word, or None if it is not sensitive.

    IPs map into the documentation range with a made-up last octet that
    keeps no part of the real address; pass one `ip_map` per run so each
    address keeps its fake. Prefix rules map whole words, literals are
    replaced inside the word (chained).
    """
    low = word.strip().lower()
    if not low:
        return None
    ip = IP_RE.match(low)
    if ip:
        lead, addr, trail = ip.groups()
        return f"{lead}{fake_ip(addr, ip_prefix, {} if ip_map is None else ip_map)}{trail}"
    for prefix, repl in (prefixes if prefixes is not None else DEFAULT_PREFIXES).items():
        if low.startswith(prefix):
            return repl
    out = low
    changed = False
    for needle, repl in (
        literals if literals is not None else DEFAULT_LITERALS
    ).items():
        if needle in out:
            out = out.replace(needle, repl)
            changed = True
    return out if changed else None


MIN_PREFIX = 6
MIN_FRAGMENT = 5
_EDGE_PUNCT = "()[]{}<>,;:\"'|"
_BORDERS = {"|", "│", "┃", "║", "¦"}
STYLES = ("replace", "box", "blur")
# TUI tab switches between sparse dark layouts change few pixels; 2% misses them
SCENE_THRESHOLD = 0.008


def _common_run(a: str, b: str) -> int:
    return SequenceMatcher(None, a, b, autojunk=False).find_longest_match(
        0, len(a), 0, len(b)).size


def match_entity(word: str, known: list[str]) -> str | None:
    """Known entity an OCR word shows: whole, cut off by a column, or as a
    fragment of a misread (e.g. an IP split into '97' and '97.15')."""
    low = word.strip().strip(_EDGE_PUNCT).lower()
    if not low:
        return None
    for entity in known:
        ent = entity.lower()
        if ent in low or (len(low) >= MIN_FRAGMENT and low in ent):
            return entity
        if len(low) >= MIN_PREFIX and _common_run(low, ent) >= MIN_PREFIX:
            return entity
    if len(low) >= MIN_FRAGMENT and set(low) <= set("0123456789."):
        # OCR misreads digits in coloured table cells; compare with every
        # same-length window of each known IP
        for entity in known:
            if IP_RE.match(entity) and any(
                SequenceMatcher(None, low, entity[i:i + len(low)]).ratio() >= 0.8
                for i in range(len(entity) - len(low) + 1)
            ):
                return entity
    return None


MAX_IP_SPAN = 17  # longest IPv4 plus slack for OCR noise


def _ip_fragment(text: str) -> bool:
    """Neighbour that may belong to a misread IP: pure digits/dots or short noise."""
    return text not in _BORDERS and (
        len(text) <= 3 or set(text) <= set("0123456789."))


def scan_tsv(
    tsv: str,
    *,
    upscale: int,
    known: list[str],
    classify: Callable[[str], str | None],
    min_conf: float = 40.0,
) -> list[tuple[str, str, tuple[int, int, int, int]]]:
    """Sensitive words in one tesseract TSV as (original, replacement, box).

    Known-entity matches ignore OCR confidence (misreads are low-confidence
    by nature); rule matches keep the threshold. A known IP extends over
    adjacent fragments on its line, stopping at table borders. Boxes are in
    video coordinates.
    """
    lines: dict[tuple[str, str, str], list[tuple[int, int, int, int, float, str]]] = {}
    for row in tsv.splitlines()[1:]:
        parts = row.split("\t")
        if len(parts) < 12 or not parts[11].strip():
            continue
        try:
            x, y, w, h = (int(parts[i]) for i in (6, 7, 8, 9))
            conf = float(parts[10])
        except ValueError:
            continue
        lines.setdefault((parts[2], parts[3], parts[4]), []).append(
            (x, y, w, h, conf, parts[11].strip()))

    hits = []
    for words in lines.values():
        words.sort()
        used: set[int] = set()
        for i, (x, y, w, h, conf, text) in enumerate(words):
            if i in used:
                continue
            entity = match_entity(text, known)
            replacement = classify(text) if conf >= min_conf else None
            if entity is None and replacement is None:
                continue
            lo = hi = i
            if entity and IP_RE.match(entity):
                limit = 1.5 * h

                def span_len(a: int, b: int) -> int:
                    return sum(len(words[k][5]) for k in range(a, b + 1))

                while lo > 0 and _ip_fragment(words[lo - 1][5]) and (
                        words[lo][0] - (words[lo - 1][0] + words[lo - 1][2]) <= limit
                ) and span_len(lo - 1, hi) <= MAX_IP_SPAN:
                    lo -= 1
                while hi < len(words) - 1 and _ip_fragment(words[hi + 1][5]) and (
                        words[hi + 1][0] - (words[hi][0] + words[hi][2]) <= limit
                ) and span_len(lo, hi + 1) <= MAX_IP_SPAN:
                    hi += 1
            used.update(range(lo, hi + 1))
            span = words[lo:hi + 1]
            x0, y0 = min(s[0] for s in span), min(s[1] for s in span)
            x1 = max(s[0] + s[2] for s in span)
            y1 = max(s[1] + s[3] for s in span)
            hits.append((
                entity or text,
                replacement or "redacted",
                (x0 // upscale, y0 // upscale,
                 (x1 - x0) // upscale, (y1 - y0) // upscale),
            ))
    return hits


def scene_window(
    t: float, scenes: list[tuple[float, float]]
) -> tuple[float, float] | None:
    """Static scene containing time t; TUI content is stable within one."""
    for start, end in scenes:
        if start <= t < end or (t == end == scenes[-1][1]):
            return (start, end)
    return None


@dataclass
class Patch:
    """One position-clustered entity: canonical replacement + time windows."""

    x: int
    y: int
    w: int
    h: int
    replacement: str
    windows: set[tuple[float, float]] = field(default_factory=set)
    bg: str = "0x042527"
    frame: Path | None = None


def _merge_windows(
    windows: set[tuple[float, float]], max_gap: float = 2.5
) -> list[tuple[float, float]]:
    """Merge overlapping/adjacent time windows into contiguous runs.

    The gap tolerance bridges single-frame OCR misses (one missed frame at
    0.5 fps would otherwise open a 2 s blink hole in the coverage).
    """
    merged: list[tuple[float, float]] = []
    for ws, we in sorted(windows):
        if merged and ws <= merged[-1][1] + max_gap:
            merged[-1] = (merged[-1][0], max(merged[-1][1], we))
        else:
            merged.append((ws, we))
    return merged


def cluster_patches(detections: list[Patch]) -> list[Patch]:
    """Merge detections at (roughly) the same position into canonical patches.

    The replacement is the majority vote across scenes, so a single OCR
    misread cannot win; windows are unioned (and merged into contiguous
    runs); geometry comes from first sight.
    """
    clustered: dict[tuple[int, int], list[Patch]] = {}
    for det in detections:
        key = (round(det.x / 24) * 24, round(det.y / 8) * 8)
        clustered.setdefault(key, []).append(det)
    patches: list[Patch] = []
    for group in clustered.values():
        counts = Counter(p.replacement for p in group)
        first = group[0]
        patches.append(
            Patch(
                x=first.x,
                y=first.y,
                w=first.w,
                h=first.h,
                replacement=counts.most_common(1)[0][0],
                windows=set(_merge_windows(
                    [w for p in group for w in p.windows]
                )),
                frame=first.frame,
            )
        )
    return patches


def bridge_windows(
    windows: set[tuple[float, float]],
    samples: list[tuple[float, "np.ndarray"]],
    *,
    duration: float,
    max_diff: float = 3.0,
    max_blind_gap: float = 2.0,
    min_ink: float = 6.0,
) -> set[tuple[float, float]]:
    """Extend a patch into gaps for as long as its region keeps the same pixels.

    A TUI redraws chrome, sidebars and tables identically, so a gap next to a
    window usually means OCR missed the text, not that it went away. From
    each window edge the patch grows sample by sample until the region
    changes, and up to the first differing sample (over-covering a fraction
    of a second is harmless, under-covering leaks). `samples` are (time,
    grayscale region) pairs; short gaps without samples are bridged. The
    reference must show text (pixel spread >= min_ink): a window can start
    before its content loaded, and empty background matches everywhere.
    """
    merged = _merge_windows(windows, max_gap=0.0)
    inside = [(t, r) for t, r in samples if any(s <= t <= e for s, e in merged)]
    if not merged or not inside:
        return set(windows)

    def inked(region: "np.ndarray") -> bool:
        return float(region.std()) >= min_ink

    def same(region: "np.ndarray", ref: "np.ndarray") -> bool:
        return inked(region) and abs(region.astype(int) - ref.astype(int)).mean() <= max_diff

    def ref_near(t: float) -> "np.ndarray | None":
        candidates = [item for item in inside if inked(item[1])]
        if not candidates:
            return None
        return min(candidates, key=lambda item: abs(item[0] - t))[1]

    # (start, end, grow from left edge, grow from right edge)
    gaps = []
    if merged[0][0] > 0:
        gaps.append((0.0, merged[0][0], False, True))
    gaps += [(b, c, True, True) for (_, b), (c, _) in zip(merged, merged[1:]) if c > b]
    if merged[-1][1] < duration:
        gaps.append((merged[-1][1], duration, True, False))

    bridged = set(windows)
    for start, end, from_left, from_right in gaps:
        within = [(t, r) for t, r in samples if start < t < end]
        if not within:
            if end - start <= max_blind_gap:
                bridged.add((start, end))
            continue
        if from_left and (ref := ref_near(start)) is not None:
            reach = start
            for t, region in within:
                if not same(region, ref):
                    reach = t
                    break
            else:
                reach = end
            if reach > start:
                bridged.add((start, reach))
        if from_right and (ref := ref_near(end)) is not None:
            reach = end
            for t, region in reversed(within):
                if not same(region, ref):
                    reach = t
                    break
            else:
                reach = start
            if reach < end:
                bridged.add((reach, end))
    return bridged


def bridge_static_gaps(
    video: str, patches: list[Patch], *, fps: float = 4.0, downscale: int = 2
) -> None:
    """Apply `bridge_windows` to every patch using one small grayscale decode."""
    import numpy as np

    probe = json.loads(run([
        "ffprobe", "-v", "error", "-select_streams", "v:0",
        "-show_entries", "stream=width,height", "-of", "json", video]).stdout)
    width = probe["streams"][0]["width"] // downscale
    height = probe["streams"][0]["height"] // downscale
    raw = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", video,
         "-vf", f"fps={fps},scale={width}:{height},format=gray",
         "-f", "rawvideo", "-"], capture_output=True, check=True).stdout
    frames = np.frombuffer(raw, dtype=np.uint8).reshape(-1, height, width)
    duration = probe_duration(video)
    for patch in patches:
        y, x = patch.y // downscale, patch.x // downscale
        region = (slice(y, y + max(patch.h // downscale, 1)),
                  slice(x, x + max(patch.w // downscale, 1)))
        samples = [(k / fps, frame[region]) for k, frame in enumerate(frames)]
        patch.windows = bridge_windows(patch.windows, samples, duration=duration)


def propagate_persistent(
    patches: list[Patch],
    scene_pairs: list[tuple[float, float]],
    *,
    tui_start: float,
    x_limit: int = 330,
) -> None:
    """Extend left-strip entities to every TUI scene (persistent sidebar)."""
    in_place = [
        p
        for p in patches
        if p.x < x_limit and any(s >= tui_start for s, _ in p.windows)
    ]
    for patch in in_place:
        patch.windows |= {(s, e) for s, e in scene_pairs if s >= tui_start}


def build_filter_chain(
    patches: list[Patch],
    font_path: str | None = None,
    *,
    max_fs: int = DEFAULT_MAX_FS,
    min_fs: int = DEFAULT_MIN_FS,
    char_w: float = DEFAULT_CHAR_W,
    style: str = "replace",
) -> str:
    """ffmpeg -vf chain gated by each patch's time windows.

    `replace` draws a background box plus replacement text; `box` blacks the
    padded region out; `blur` overlays a blurred crop of it. The padding
    covers glyph edges that OCR boxes cut off.
    """
    if style not in STYLES:
        raise ValueError(f"Unknown redaction style '{style}' (known: {', '.join(STYLES)})")
    if style != "replace":
        return _obscure_chain(patches, style)
    font_path = font_path or default_font()
    chain = []
    for patch in patches:
        fs = min(max(int(patch.h * 0.95), min_fs), max_fs)
        h = min(patch.h, 40)
        w = max(patch.w, int(len(patch.replacement) * char_w * fs)) + int(
            2 * char_w * fs
        )
        text_y = patch.y + max((h - fs) // 2, 0)
        for start, end in sorted(patch.windows):
            enable = f"enable='between(t,{start},{end})'"
            chain.append(
                f"drawbox=x={patch.x}:y={patch.y}:w={w}:h={h}"
                f":color={patch.bg}:t=fill:{enable}"
            )
            chain.append(
                f"drawtext=fontfile={font_path}:fontsize={fs}"
                f":fontcolor=0xE6EDF7:expansion=none:x={patch.x + 2}:y={text_y}"
                f":text={_drawtext_literal(patch.replacement)}:{enable}"
            )
    return ",".join(chain)


def _obscure_chain(patches: list[Patch], style: str) -> str:
    """Black boxes, or one full-frame blur merged through a timed box mask.

    The blur deliberately avoids a split/overlay pair per patch: long chains
    of those stall ffmpeg's filter graph.
    """
    boxes = []
    sigma = 6
    for patch in patches:
        pad_x, pad_y = round(patch.h * 0.5), round(patch.h * 0.3)
        x, y = max(patch.x - pad_x, 0), max(patch.y - pad_y, 0)
        w, h = patch.w + 2 * pad_x, patch.h + 2 * pad_y
        enable = "+".join(
            f"between(t,{start},{end})" for start, end in sorted(patch.windows))
        color = "black" if style == "box" else "white"
        boxes.append(
            f"drawbox=x={x}:y={y}:w={w}:h={h}:color={color}:t=fill:enable='{enable}'")
        sigma = max(sigma, round(patch.h * 0.6))
    if style == "box" or not boxes:
        return ",".join(boxes)
    return (
        "split=3[rdbase][rdsrc][rdmask];"
        f"[rdsrc]gblur=sigma={sigma}:steps=2,format=gbrp[rdblur];"
        "[rdmask]format=gbrp,drawbox=x=0:y=0:w=iw:h=ih:color=black:t=fill,"
        f"{','.join(boxes)}[rdm];"
        "[rdbase]format=gbrp[rdorig];"
        "[rdorig][rdblur][rdm]maskedmerge,format=yuv420p"
    )


# --- IO stages -------------------------------------------------------


def run(cmd: list[str], **kw) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, check=True, capture_output=True, text=True, **kw)


def detect_scenes(video: str, threshold: float = 0.02) -> list[float]:
    """Scene-change times via ffmpeg scene detection."""
    proc = subprocess.run(
        ["ffmpeg", "-v", "info", "-i", video,
         "-vf", f"select='gt(scene,{threshold})',showinfo", "-f", "null", "-"],
        capture_output=True, text=True)
    times = [float(m) for m in re.findall(r"pts_time:([0-9.]+)", proc.stderr)]
    return sorted(set(times))


def scene_pairs(times: list[float], duration: float) -> list[tuple[float, float]]:
    bounds = sorted(set([0.0] + times + [duration]))
    return [(bounds[i], bounds[i + 1]) for i in range(len(bounds) - 1)]


def probe_duration(video: str) -> float:
    proc = run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                "-of", "json", video])
    return float(json.loads(proc.stdout)["format"]["duration"])


def extract_frames(
    video: str, out_dir: Path, fps: float = 1, scale: int = 1
) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    for stale in out_dir.glob("f*.png"):
        stale.unlink()
    for stale in out_dir.glob("f*.tsv"):
        stale.unlink()
    vf = f"fps={fps}"
    if scale > 1:
        vf += f",scale=iw*{scale}:ih*{scale}:flags=lanczos"
    run(["ffmpeg", "-v", "error", "-i", video, "-vf", vf,
         str(out_dir / "f%02d.png")])
    return sorted(out_dir.glob("f*.png"))


def extract_frames_at(
    video: str, times: list[float], out_dir: Path, scale: int = 1
) -> list[tuple[float, Path]]:
    """One (upscaled) frame per requested time, e.g. right after scene changes."""
    out_dir.mkdir(parents=True, exist_ok=True)
    for stale in [*out_dir.glob("s*.png"), *out_dir.glob("s*.tsv")]:
        stale.unlink()
    vf = f"scale=iw*{scale}:ih*{scale}:flags=lanczos" if scale > 1 else "null"
    frames = []
    for n, t in enumerate(times, 1):
        frame = out_dir / f"s{n:03d}.png"
        run(["ffmpeg", "-v", "error", "-ss", f"{t:.3f}", "-i", video,
             "-frames:v", "1", "-vf", vf, "-y", str(frame)])
        frames.append((t, frame))
    return frames


def sample_bg(frame: str, x: int, y: int, w: int, h: int) -> str:
    """Background color just left of the text box, vertically centered."""
    px, py = max(x - 4, 0), min(y + h // 2, 4095)
    out = subprocess.run(
        ["ffmpeg", "-v", "quiet", "-i", frame, "-vf", f"crop=1:1:{px}:{py}",
         "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
        capture_output=True).stdout
    if len(out) >= 3:
        return f"0x{out[0]:02X}{out[1]:02X}{out[2]:02X}"
    return "0x042527"


def _frame_tsv(frame: Path) -> str:
    """OCR one frame (psm 6, upscaled), cached on disk next to the frame."""
    cache = frame.with_suffix(".tsv")
    if cache.exists():
        return cache.read_text()
    proc = run(
        ["tesseract", str(frame), "-", "--psm", "6", "tsv"],
        env={**os.environ, "OMP_THREAD_LIMIT": "1"})
    cache.write_text(proc.stdout)
    return proc.stdout


def _scan_video(
    video: str,
    frames_dir: Path,
    *,
    known: list[str],
    classify: Callable[[str], str | None],
    fps: float,
    upscale: int,
    min_conf: float,
    workers: int,
    scene_threshold: float,
) -> tuple[list[Patch], set[str]]:
    """OCR periodic and post-scene-change frames; return detections + originals.

    Since TUI content is static within a scene, a sample stands for its
    whole scene (or its neighbourhood if no scene contains it).
    """
    from concurrent.futures import ThreadPoolExecutor

    scenes = scene_pairs(detect_scenes(video, scene_threshold), probe_duration(video))
    period = 1 / fps
    periodic = extract_frames(video, frames_dir, fps=fps, scale=upscale)
    samples = [((int(f.stem[1:]) - 0.5) * period, f) for f in periodic]
    samples += extract_frames_at(
        video, [min(s + 0.2, e) for s, e in scenes[1:]], frames_dir, scale=upscale)
    with ThreadPoolExecutor(max_workers=workers) as pool:
        tsvs = list(pool.map(_frame_tsv, [frame for _, frame in samples]))

    detections: list[Patch] = []
    originals: set[str] = set()
    for (t, frame), tsv in zip(samples, tsvs):
        # the scene bounds the sample: a neighbourhood window would spill
        # patches onto the previous screen across a scene change
        scene = scene_window(t, scenes)
        windows = {scene} if scene else {(max(t - period, 0.0), t + period)}
        for original, replacement, (x, y, w, h) in scan_tsv(
                tsv, upscale=upscale, known=known, classify=classify,
                min_conf=min_conf):
            originals.add(original)
            detections.append(Patch(x=x, y=y, w=w, h=h, replacement=replacement,
                                    windows=set(windows), frame=frame))
    return detections, originals


def _patch_dict(p: Patch) -> dict:
    return {
        "x": p.x, "y": p.y, "w": p.w, "h": p.h,
        "replacement": p.replacement,
        "bg": p.bg,
        "windows": [list(w) for w in sorted(p.windows)],
    }


def detect(
    video: str,
    work_dir: Path,
    *,
    literals: dict[str, str] | None = None,
    prefixes: dict[str, str] | None = None,
    ip_prefix: str = DEFAULT_IP_PREFIX,
    min_conf: float = 40.0,
    upscale: int = 3,
    workers: int = 4,
    fps: float = 1.0,
    entities: list[str] | None = None,
    style: str = "replace",
    scene_threshold: float = SCENE_THRESHOLD,
) -> dict:
    """Full detection pass: frames → OCR → classify → clustered patches.

    Frames are upscaled before OCR — small sidebar text is invisible to
    tesseract at native resolution; 3x matches the `verify` gate so both
    read the same text. Frames are sampled periodically and right after
    every scene change; a word is sensitive if a redaction rule classifies
    it or it shows a known project entity. Since TUI content is static
    within a scene, each detection covers its whole scene. TSV results are
    cached per frame, so interrupted runs resume where they stopped.
    """
    if style not in STYLES:
        raise ValueError(f"Unknown redaction style '{style}' (known: {', '.join(STYLES)})")
    literals = {**DEFAULT_LITERALS, **(literals or {})}
    prefixes = {**DEFAULT_PREFIXES, **(prefixes or {})}

    ip_map: dict[str, str] = {}

    def classify(word: str) -> str | None:
        return classify_word(
            word, literals=literals, prefixes=prefixes, ip_prefix=ip_prefix,
            ip_map=ip_map)

    detections, originals = _scan_video(
        video, work_dir / "frames", known=list(entities or []), classify=classify,
        fps=fps, upscale=upscale, min_conf=min_conf, workers=workers,
        scene_threshold=scene_threshold)

    patches = cluster_patches(detections)
    bridge_static_gaps(video, patches)
    for patch in patches:
        if style != "replace" or patch.frame is None:
            continue
        patch.bg = sample_bg(
            str(patch.frame),
            patch.x * upscale, patch.y * upscale,
            patch.w * upscale, patch.h * upscale)

    payload = {
        "style": style,
        "originals": sorted(originals, key=str.lower),
        "patches": [_patch_dict(p) for p in patches],
    }
    work_dir.mkdir(parents=True, exist_ok=True)
    (work_dir / "redaction.json").write_text(json.dumps(payload, indent=2))
    return payload


def load_patches(work_dir: Path) -> tuple[list[str], list[Patch]]:
    """Read redaction.json back into originals + patches."""
    data = json.loads((work_dir / "redaction.json").read_text())
    patches = [
        Patch(x=p["x"], y=p["y"], w=p["w"], h=p["h"], replacement=p["replacement"],
              windows={tuple(w) for w in p["windows"]},
              bg=p.get("bg", "0x042527"))
        for p in data["patches"]
    ]
    return data["originals"], patches


def load_style(work_dir: Path) -> str:
    """Redaction style recorded in redaction.json (legacy files: replace)."""
    path = work_dir / "redaction.json"
    if not path.exists():
        return "replace"
    return json.loads(path.read_text()).get("style", "replace")


def apply(
    video: str, work_dir: Path, out: str | Path | None = None,
    *, style: str | None = None,
) -> Path:
    originals, patches = load_patches(work_dir)
    chain = build_filter_chain(patches, style=style or load_style(work_dir))
    out = Path(out or work_dir / "redacted.mp4")
    run(["ffmpeg", "-v", "error", "-i", video, "-vf", chain,
         "-c:v", "libx264", "-crf", "20", "-preset", "medium", "-c:a", "copy",
         "-y", str(out)])
    return out


def refine(
    video: str,
    work_dir: Path,
    *,
    entities: list[str] | None = None,
    rounds: int = 2,
    fps: float = 1.0,
    upscale: int = 3,
    workers: int = 4,
    scene_threshold: float = SCENE_THRESHOLD,
) -> int:
    """Apply, OCR the redacted result, patch whatever is still readable; repeat.

    Only originals and known entities are searched, so replacement text can
    never trigger another round. Returns the number of patches added.
    """
    path = work_dir / "redaction.json"
    added = 0
    for _ in range(rounds):
        redacted = apply(video, work_dir)
        data = json.loads(path.read_text())
        known = sorted(set(data["originals"]) | set(entities or []), key=str.lower)
        detections, originals = _scan_video(
            str(redacted), work_dir / "refine-frames", known=known,
            classify=lambda word: None, fps=fps, upscale=upscale, min_conf=0.0,
            workers=workers, scene_threshold=scene_threshold)
        if not detections:
            return added
        new = cluster_patches(detections)
        _, existing = load_patches(work_dir)
        everything = existing + new
        bridge_static_gaps(video, everything)
        data["patches"] = [_patch_dict(p) for p in everything]
        data["originals"] = sorted(set(data["originals"]) | originals, key=str.lower)
        path.write_text(json.dumps(data, indent=2))
        added += len(new)
    apply(video, work_dir)
    return added
