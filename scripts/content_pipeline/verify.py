"""Verify stage: the publish leak gate. OCRs final artifacts and fails if
any original (un-redacted) entity survived anywhere."""

from __future__ import annotations

from pathlib import Path

from scripts.content_pipeline import entities, redact, transcribe as stt


def verify(artifacts: list[str | Path], work_dir: Path) -> list[str]:
    """Return leak descriptions; an empty list means the gate passes."""
    originals: list[str] = []
    if (work_dir / "redaction.json").exists():
        originals, _ = redact.load_patches(work_dir)
    # known project entities must stay unreadable even if detection missed them
    originals = sorted(set(originals) | set(entities.load(work_dir)), key=str.lower)
    if not originals:
        return []
    leaks: list[str] = []
    # audio track: narration mentioning an original entity
    if (work_dir / "transcript.json").exists():
        segments = stt.load_transcript(work_dir)
        leaks.extend(
            f"audio: mentioned '{original}'"
            for original in stt.transcript_leaks(originals, segments)
        )
    for artifact in artifacts:
        # upscale before OCR — small sidebar text is invisible at native size
        frames = redact.extract_frames(
            str(artifact), work_dir / "verify-frames", fps=1.0, scale=3)
        for frame in frames:
            text = redact.run(
                ["tesseract", str(frame), "-", "--psm", "6"]).stdout
            low = text.lower()
            for original in originals:
                if original.lower() in low:
                    leaks.append(
                        f"{Path(artifact).name}: leaked '{original}' ({frame.name})"
                    )
    return sorted(set(leaks))
