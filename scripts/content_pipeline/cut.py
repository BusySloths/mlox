"""Cut stage: timeline/range-driven artifact extraction (clips, screenshots,
GIFs), applying the reviewed redaction chain while cutting.

All cutting uses input seeking (-ss before -i), which resets timestamps —
redaction windows are therefore shifted into segment-local time, and the
chain is merged into every single -vf/-filter_complex (a second -vf would
silently override the first).
"""

from __future__ import annotations

import dataclasses
from pathlib import Path

from scripts.content_pipeline import redact


def _redaction_vf(
    work_dir: Path | None,
    *,
    seg_start: float | None = None,
    seg_end: float | None = None,
    at: float | None = None,
) -> str | None:
    """Redaction -vf value for the requested segment/instant, or None.

    Time windows are shifted into segment-local time (input seeking resets
    timestamps) and dropped when they do not intersect the segment.
    """
    if work_dir is None or not (work_dir / "redaction.json").exists():
        return None
    _, patches = redact.load_patches(work_dir)
    if at is not None:
        patches = [
            dataclasses.replace(p, windows={(0.0, 1e9)})
            for p in patches
            if any(ws <= at < we for ws, we in p.windows)
        ]
    elif seg_start is not None and seg_end is not None:
        shifted = []
        for patch in patches:
            windows = [
                (max(ws, seg_start) - seg_start, min(we, seg_end) - seg_start)
                for ws, we in patch.windows
                if ws < seg_end and we > seg_start
            ]
            if windows:
                shifted.append(dataclasses.replace(patch, windows=set(windows)))
        patches = shifted
    if not patches:
        return None
    return redact.build_filter_chain(patches, style=redact.load_style(work_dir))


def _base_filters(fps: int, width: int) -> str:
    return f"fps={fps},scale={width}:-1:flags=lanczos"


def screenshot(
    video: str, at: float, out: str | Path, work_dir: Path | None = None
) -> Path:
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    red_vf = _redaction_vf(work_dir, at=at)
    cmd = ["ffmpeg", "-v", "error", "-y", "-ss", str(at), "-i", video]
    if red_vf:
        cmd += ["-vf", red_vf]
    cmd += ["-frames:v", "1", str(out)]
    redact.run(cmd)
    return out


def gif(
    video: str, start: float, end: float, out: str | Path,
    work_dir: Path | None = None, *, fps: int = 12, width: int = 960,
    max_colors: int = 128,
) -> Path:
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    red_vf = _redaction_vf(work_dir, seg_start=start, seg_end=end)
    pre = _base_filters(fps, width)
    if red_vf:
        pre = f"{red_vf},{pre}"
    palette = str(out.with_suffix(".palette.png"))
    redact.run([
        "ffmpeg", "-v", "error", "-y", "-ss", str(start), "-to", str(end),
        "-i", video, "-vf", f"{pre},palettegen=max_colors={max_colors}",
        palette,
    ])
    redact.run([
        "ffmpeg", "-v", "error", "-y", "-ss", str(start), "-to", str(end),
        "-i", video, "-i", palette,
        "-filter_complex",
        f"[0:v]{pre}[x];[x][1:v]paletteuse=dither=bayer:bayer_scale=4[out]",
        "-map", "[out]", str(out),
    ])
    Path(palette).unlink(missing_ok=True)
    return out


def clip(
    video: str, start: float, end: float, out: str | Path,
    work_dir: Path | None = None,
) -> Path:
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    red_vf = _redaction_vf(work_dir, seg_start=start, seg_end=end)
    cmd = ["ffmpeg", "-v", "error", "-y", "-ss", str(start), "-to", str(end),
           "-i", video]
    if red_vf:
        cmd += ["-vf", red_vf]
    cmd += ["-c:v", "libx264", "-crf", "20", "-c:a", "copy", str(out)]
    redact.run(cmd)
    return out
