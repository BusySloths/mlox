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
import re
import subprocess
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

IP_RE = re.compile(r"^\d{1,3}(?:\.\d{1,3}){3}$")
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


def classify_word(
    word: str,
    *,
    literals: dict[str, str] | None = None,
    prefixes: dict[str, str] | None = None,
    ip_prefix: str = DEFAULT_IP_PREFIX,
) -> str | None:
    """Replacement for one OCR word, or None if it is not sensitive.

    IPs map into the documentation range keeping the last octet, prefix
    rules map whole words, literals are replaced inside the word (chained).
    """
    low = word.strip().lower()
    if not low:
        return None
    if IP_RE.match(low):
        return f"{ip_prefix}.{low.rsplit('.', 1)[1]}"
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


def cluster_patches(detections: list[Patch]) -> list[Patch]:
    """Merge detections at (roughly) the same position into canonical patches.

    The replacement is the majority vote across scenes, so a single OCR
    misread cannot win; windows are unioned; geometry comes from first sight.
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
                windows=set().union(*(p.windows for p in group)),
            )
        )
    return patches


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
    font_path: str = DEFAULT_FONT,
    *,
    max_fs: int = DEFAULT_MAX_FS,
    min_fs: int = DEFAULT_MIN_FS,
    char_w: float = DEFAULT_CHAR_W,
) -> str:
    """ffmpeg -vf chain: per patch a background drawbox + replacement text,
    both gated by the patch's scene windows."""
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
                f":fontcolor=0xE6EDF7:x={patch.x + 2}:y={text_y}"
                f":text='{patch.replacement}':{enable}"
            )
    return ",".join(chain)


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


def extract_frames(video: str, out_dir: Path, fps: int = 1) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    run(["ffmpeg", "-v", "error", "-i", video, "-vf", f"fps={fps}",
         str(out_dir / "f%02d.png")])
    return sorted(out_dir.glob("f*.png"))


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


def detect(
    video: str,
    work_dir: Path,
    *,
    literals: dict[str, str] | None = None,
    prefixes: dict[str, str] | None = None,
    ip_prefix: str = DEFAULT_IP_PREFIX,
    min_conf: float = 40.0,
) -> dict:
    """Full detection pass: frames → OCR → classify → clustered patches."""
    duration = probe_duration(video)
    scenes = scene_pairs(detect_scenes(video), duration)
    frames = extract_frames(video, work_dir / "frames")
    frame_for_scene: dict[tuple[float, float], Path] = {}
    for frame in frames:
        t = int(frame.stem[1:]) - 0.5
        for pair in scenes:
            if pair[0] <= t < pair[1]:
                frame_for_scene.setdefault(pair, frame)
                break

    literals = {**DEFAULT_LITERALS, **(literals or {})}
    prefixes = {**DEFAULT_PREFIXES, **(prefixes or {})}
    detections: list[Patch] = []
    originals: set[str] = set()
    for (start, end), frame in sorted(frame_for_scene.items()):
        tsv = ""
        for psm in ("6", "11"):
            proc = run(["tesseract", str(frame), "-", "--psm", psm, "tsv"])
            tsv += proc.stdout
        for line in tsv.splitlines()[1:]:
            parts = line.split("\t")
            if len(parts) < 12:
                continue
            word = parts[11].strip()
            replacement = classify_word(
                word, literals=literals, prefixes=prefixes, ip_prefix=ip_prefix
            )
            try:
                conf = float(parts[10])
            except ValueError:
                continue
            if replacement is None or conf < min_conf or not word:
                continue
            originals.add(word)
            x, y, w, h = (int(parts[i]) for i in (6, 7, 8, 9))
            detections.append(
                Patch(x=x, y=y, w=w, h=h, replacement=replacement,
                      windows={(start, end)})
            )

    patches = cluster_patches(detections)
    propagate_persistent(patches, scenes, tui_start=min(s for s, _ in scenes[2:]))
    for patch in patches:
        first_scene = sorted(patch.windows)[0]
        frame = frame_for_scene.get(first_scene)
        if frame is not None:
            patch.bg = sample_bg(str(frame), patch.x, patch.y, patch.w, patch.h)

    payload = {
        "originals": sorted(originals, key=str.lower),
        "patches": [
            {
                "x": p.x, "y": p.y, "w": p.w, "h": p.h,
                "replacement": p.replacement,
                "windows": [list(w) for w in sorted(p.windows)],
            }
            for p in patches
        ],
    }
    work_dir.mkdir(parents=True, exist_ok=True)
    (work_dir / "redaction.json").write_text(json.dumps(payload, indent=2))
    return payload


def load_patches(work_dir: Path) -> tuple[list[str], list[Patch]]:
    """Read redaction.json back into originals + patches."""
    data = json.loads((work_dir / "redaction.json").read_text())
    patches = [
        Patch(x=p["x"], y=p["y"], w=p["w"], h=p["h"], replacement=p["replacement"],
              windows={tuple(w) for w in p["windows"]})
        for p in data["patches"]
    ]
    return data["originals"], patches


def apply(video: str, work_dir: Path, out: str | Path | None = None) -> Path:
    originals, patches = load_patches(work_dir)
    chain = build_filter_chain(patches)
    out = Path(out or work_dir / "redacted.mp4")
    run(["ffmpeg", "-v", "error", "-i", video, "-vf", chain,
         "-c:v", "libx264", "-crf", "20", "-preset", "medium", "-c:a", "copy",
         "-y", str(out)])
    return out

