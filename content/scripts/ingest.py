"""Ingest stage: probe a recording against the recording preset."""

from __future__ import annotations

import json
import subprocess


def probe(video: str) -> dict:
    proc = subprocess.run(
        ["ffprobe", "-v", "error", "-show_format", "-show_streams", "-of", "json",
         video],
        capture_output=True, text=True, check=True)
    data = json.loads(proc.stdout)
    streams = {s["codec_type"]: s for s in data.get("streams", [])}
    video = streams.get("video", {})
    audio = streams.get("audio", {})
    return {
        "width": video.get("width"),
        "height": video.get("height"),
        "fps": video.get("avg_frame_rate"),
        "pix_fmt": video.get("pix_fmt"),
        "codec": video.get("codec_name"),
        "bit_rate": int(video.get("bit_rate") or 0),
        "duration": float(data.get("format", {}).get("duration") or 0),
        "audio": {
            "codec": audio.get("codec_name"),
            "sample_rate": audio.get("sample_rate"),
        } if audio else None,
    }


def check(probe_data: dict, preset: dict) -> list[str]:
    """Warn about anything violating the recording preset."""
    warnings = []
    recording = preset.get("recording", {})
    min_height = recording.get("min_height", 1080)
    if (probe_data.get("height") or 0) < min_height:
        warnings.append(
            f"Resolution {probe_data.get('width')}x{probe_data.get('height')} "
            f"is below the preset minimum height {min_height}."
        )
    fps_raw = str(probe_data.get("fps") or "0/1")
    try:
        num, den = fps_raw.split("/")
        fps = float(num) / float(den)
    except (ValueError, ZeroDivisionError):
        fps = 0.0
    max_fps = recording.get("max_fps", 30)
    if fps > max_fps + 1:
        warnings.append(f"FPS {fps:.0f} exceeds {max_fps} (wasted on a TUI).")
    if probe_data.get("pix_fmt") not in (None, "yuv420p"):
        warnings.append(f"Pixel format {probe_data.get('pix_fmt')} — prefer yuv420p.")
    if not probe_data.get("audio"):
        warnings.append("No audio track found.")
    return warnings
