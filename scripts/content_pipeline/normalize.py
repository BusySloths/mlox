"""Normalize a local capture into the reproducible pipeline working master."""

from __future__ import annotations

import subprocess
from pathlib import Path


def video_filter(max_width: int, max_height: int, fps: int) -> str:
    """Return a high-quality, aspect-ratio-preserving working-master filter."""
    if min(max_width, max_height, fps) <= 0:
        raise ValueError("max_width, max_height, and fps must be positive.")
    return (
        f"scale=w='min(iw,{max_width})':h='min(ih,{max_height})'"
        ":force_original_aspect_ratio=decrease:force_divisible_by=2:flags=lanczos,"
        f"fps={fps}"
    )


def normalize(
    video: str | Path,
    out: str | Path,
    *,
    max_width: int = 1920,
    max_height: int = 1440,
    fps: int = 30,
) -> Path:
    """Create the local H.264/yuv420p working master from a source capture.

    The source recording remains untouched. Later visual stages must use this
    file so OCR, redaction geometry, and final artifacts share one resolution.
    """
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            "ffmpeg", "-v", "error", "-y", "-i", str(video),
            "-map", "0:v:0", "-map", "0:a?",
            "-vf", video_filter(max_width, max_height, fps),
            "-c:v", "libx264", "-crf", "18", "-preset", "medium",
            "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k",
            "-movflags", "+faststart", str(out),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return out
