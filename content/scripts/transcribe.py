"""Transcribe stage: speech-to-text for the content pipeline.

Uses OpenAI gpt-4o-mini-transcribe (~$0.18/audio-hour). The transcript
serves three consumers: chapter-marker extraction for the align stage,
captions.srt for rendered clips, and the audio leak check in verify.

gpt-4o-mini-transcribe does not reliably return segment timestamps via
verbose_json, so transcription falls back to chunked mode: the audio is
sliced into `chunk_seconds` pieces, each transcribed as plain text, and
segments are synthesized at chunk boundaries (± chunk_seconds precision —
plenty for markers, coarse but usable for captions).
"""

from __future__ import annotations

import json
import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

import requests

API_URL = "https://api.openai.com/v1/audio/transcriptions"
DEFAULT_MODEL = "gpt-4o-mini-transcribe"
DEFAULT_LANGUAGE = "en"
DEFAULT_CHUNK_SECONDS = 30.0

MARKER_RE = re.compile(r"chapter[\s:,-]+([a-z0-9-]+)")


@dataclass
class Segment:
    start: float
    end: float
    text: str


def extract_audio(video: str, out: str | Path) -> Path:
    """Extract narration audio: Opus in Ogg, mono, 16 kHz (~2 MB / 10 min)."""
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["ffmpeg", "-v", "error", "-y", "-i", video, "-vn",
         "-c:a", "libopus", "-b:a", "24k", "-ar", "16000", "-ac", "1",
         str(out)],
        check=True, capture_output=True)
    return out


def _post_multipart(api_key: str, audio_path: Path, model: str,
                    language: str) -> dict:
    with open(audio_path, "rb") as fh:
        response = requests.post(
            API_URL,
            headers={"Authorization": f"Bearer {api_key}"},
            files={"file": (audio_path.name, fh, "audio/ogg")},
            data={"model": model, "language": language,
                  "response_format": "verbose_json"},
            timeout=600,
        )
    response.raise_for_status()
    return response.json()


def _transcribe_chunk(api_key: str, audio_path: Path, model: str,
                      language: str) -> str:
    with open(audio_path, "rb") as fh:
        response = requests.post(
            API_URL,
            headers={"Authorization": f"Bearer {api_key}"},
            files={"file": (audio_path.name, fh, "audio/ogg")},
            data={"model": model, "language": language,
                  "response_format": "json"},
            timeout=600,
        )
    response.raise_for_status()
    return response.json().get("text", "")


def _slice_audio(audio: str | Path, out_dir: Path, seconds: float) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["ffmpeg", "-v", "error", "-y", "-i", str(audio), "-f", "segment",
         "-segment_time", str(seconds), "-c", "copy",
         str(out_dir / "chunk-%03d.ogg")],
        check=True, capture_output=True)
    return sorted(out_dir.glob("chunk-*.ogg"))


def transcribe(
    audio: str | Path,
    *,
    api_key: str | None = None,
    model: str = DEFAULT_MODEL,
    language: str = DEFAULT_LANGUAGE,
    chunk_seconds: float = DEFAULT_CHUNK_SECONDS,
    mode: str = "chunked",
    work_dir: Path | None = None,
    post_multipart=_post_multipart,
) -> list[Segment]:
    """Transcribe narration audio into timed segments.

    mode="chunked" (default; required for gpt-4o-mini-transcribe, which
    only returns json/text) slices the audio into chunk_seconds pieces
    and synthesizes segment boundaries at chunk edges. mode="verbose"
    reads structured segments from verbose_json (works for whisper-1).
    """
    api_key = api_key or os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is not set.")

    audio = Path(audio)
    if mode == "verbose":
        verbose = post_multipart(api_key, audio, model, language)
        segments = [
            Segment(start=float(s["start"]), end=float(s["end"]),
                    text=str(s["text"]).strip())
            for s in verbose.get("segments") or []
        ]
        if segments:
            return segments
        raise RuntimeError("verbose_json returned no segments.")

    if work_dir is None:
        raise RuntimeError("Chunked mode needs work_dir.")
    chunks = _slice_audio(audio, work_dir / "audio-chunks", chunk_seconds)
    segments = []
    for index, chunk in enumerate(chunks):
        text = _transcribe_chunk(api_key, chunk, model, language).strip()
        start = index * chunk_seconds
        segments.append(Segment(start=start, end=start + chunk_seconds,
                                text=text))
    return segments


def extract_markers(segments: list[Segment]) -> list[tuple[str, float]]:
    """Spoken `chapter <name>` markers → (name, seconds) in order."""
    markers = []
    for segment in segments:
        match = MARKER_RE.search(segment.text.lower())
        if match:
            markers.append((match.group(1), segment.start))
    return markers


def _fmt_srt(seconds: float) -> str:
    millis = int(round(seconds * 1000))
    hours, millis = divmod(millis, 3_600_000)
    minutes, millis = divmod(millis, 60_000)
    secs, millis = divmod(millis, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def srt_from_segments(segments: list[Segment]) -> str:
    """Render segments as an SRT subtitle file."""
    blocks = []
    for index, segment in enumerate(segments, start=1):
        text = segment.text.strip()
        if not text:
            continue
        blocks.append(
            f"{index}\n{_fmt_srt(segment.start)} --> {_fmt_srt(segment.end)}\n"
            f"{text}\n"
        )
    return "\n".join(blocks)


def save_transcript(segments: list[Segment], work_dir: Path) -> tuple[Path, Path]:
    work_dir.mkdir(parents=True, exist_ok=True)
    transcript = work_dir / "transcript.json"
    transcript.write_text(json.dumps(
        {"segments": [{"start": s.start, "end": s.end, "text": s.text}
                      for s in segments]},
        indent=2))
    captions = work_dir / "captions.srt"
    captions.write_text(srt_from_segments(segments))
    return transcript, captions


def load_transcript(work_dir: Path) -> list[Segment]:
    data = json.loads((work_dir / "transcript.json").read_text())
    return [Segment(start=s["start"], end=s["end"], text=s["text"])
            for s in data["segments"]]


def transcript_leaks(originals: list[str], segments: list[Segment]) -> list[str]:
    """Audio leak check: original entities mentioned in the narration."""
    text = " ".join(segment.text for segment in segments).lower()
    return sorted(
        original for original in originals
        if original and original.lower() in text
    )
