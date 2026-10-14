"""Cut stage: timeline/range-driven artifact extraction (clips, screenshots,
GIFs), applying the reviewed redaction chain while cutting."""

from __future__ import annotations

from pathlib import Path

from scripts.content_pipeline import redact


def _input_with_redaction(video: str, work_dir: Path | None) -> list[str]:
    if work_dir and (work_dir / "redaction.json").exists():
        _, patches = redact.load_patches(work_dir)
        chain = redact.build_filter_chain(patches)
        return ["-vf", chain]
    return []


def screenshot(
    video: str, at: float, out: str | Path, work_dir: Path | None = None
) -> Path:
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    red = _input_with_redaction(video, work_dir)
    redact.run(
        ["ffmpeg", "-v", "error", "-y", "-ss", str(at), "-i", video, *red,
         "-frames:v", "1", str(out)])
    return out


def gif(
    video: str, start: float, end: float, out: str | Path,
    work_dir: Path | None = None, *, fps: int = 12, width: int = 960,
    max_colors: int = 128,
) -> Path:
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    red = _input_with_redaction(video, work_dir)
    filters = f"fps={fps},scale={width}:-1:flags=lanczos"
    redact.run([
        "ffmpeg", "-v", "error", "-y", "-ss", str(start), "-to", str(end),
        "-i", video, *red, "-vf", f"{filters},palettegen=max_colors={max_colors}",
        str(out.with_suffix(".palette.png")),
    ])
    redact.run([
        "ffmpeg", "-v", "error", "-y", "-ss", str(start), "-to", str(end),
        "-i", video, "-i", str(out.with_suffix(".palette.png")),
        "-lavfi", f"{filters}[x];[x][1:v]paletteuse=dither=bayer:bayer_scale=4",
        str(out),
    ])
    out.with_suffix(".palette.png").unlink(missing_ok=True)
    return out


def clip(
    video: str, start: float, end: float, out: str | Path,
    work_dir: Path | None = None,
) -> Path:
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    red = _input_with_redaction(video, work_dir)
    redact.run([
        "ffmpeg", "-v", "error", "-y", "-ss", str(start), "-to", str(end),
        "-i", video, *red, "-c:v", "libx264", "-crf", "20", "-c:a", "copy",
        str(out),
    ])
    return out
