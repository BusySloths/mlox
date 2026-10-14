"""Verify stage: the publish leak gate. OCRs final artifacts and fails if
any original (un-redacted) entity survived anywhere."""

from __future__ import annotations

from pathlib import Path

from scripts.content_pipeline import redact


def verify(artifacts: list[str | Path], work_dir: Path) -> list[str]:
    """Return leak descriptions; an empty list means the gate passes."""
    originals, _ = redact.load_patches(work_dir)
    if not originals:
        return []
    leaks: list[str] = []
    for artifact in artifacts:
        frames = redact.extract_frames(
            str(artifact), work_dir / "verify-frames", fps=0.5)
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
