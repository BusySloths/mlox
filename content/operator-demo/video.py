"""Render the operator demo as a narrated slide video.

    uv run python -m content.operator-demo.video [--pdf DECK.pdf] [--out OUT.mp4]

Each `## Chapter:` in script.md is one deck slide, in order; its blockquote is
voiced with OpenAI text-to-speech (OPENAI_API_KEY, read from the repo .env when
unset) and the slide is held for the length of the narration. Voice clips are
cached by text, so re-rendering after an edit only voices the changed chapters.
Everything is written to content/.work/operator-demo/ (outside git).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import urllib.request
from pathlib import Path

from content.scripts.__main__ import load_env_file

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
WORK = REPO / "content" / ".work" / "operator-demo"
MODEL, VOICE = "gpt-4o-mini-tts", "onyx"
TONE = "Calm, confident product demo narrator. Clear and unhurried, warm but not salesy."
LEAD, TAIL, FADE = 0.6, 0.9, 0.4  # seconds of silence before/after each line, fade length
# Spoken forms for names the voice gets wrong; the script keeps the written form.
SAY = {"MLOX": "em-lox", "OpenBao": "Open Bao"}


def chapters(script: Path) -> list[tuple[str, str]]:
    parts = re.split(r"^## Chapter:\s*(.+)$", script.read_text(encoding="utf-8"), flags=re.M)[1:]
    result = []
    for name, body in zip(parts[::2], parts[1::2]):
        quote = " ".join(line.lstrip("> ").strip() for line in body.splitlines() if line.startswith(">"))
        result.append((name.strip(), quote.strip()))
    return result


def voice(text: str, cache: Path) -> Path:
    for written, spoken in SAY.items():
        text = re.sub(rf"\b{written}\b", spoken, text)
    key = hashlib.sha256(json.dumps([MODEL, VOICE, TONE, text]).encode()).hexdigest()[:16]
    path = cache / f"{key}.wav"
    if path.exists():
        return path
    request = urllib.request.Request(
        "https://api.openai.com/v1/audio/speech",
        data=json.dumps({"model": MODEL, "voice": VOICE, "input": text,
                         "instructions": TONE, "response_format": "wav"}).encode(),
        headers={"Authorization": f"Bearer {os.environ['OPENAI_API_KEY']}",
                 "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=120) as response:
        path.write_bytes(response.read())
    return path


def duration(path: Path) -> float:
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                          "-of", "csv=p=0", str(path)], capture_output=True, text=True, check=True)
    return float(out.stdout)


def render(pdf: Path, out: Path) -> None:
    load_env_file(REPO)
    script = chapters(HERE / "script.md")
    slides_dir, cache, clips_dir = WORK / "slides", WORK / "voice", WORK / "clips"
    for d in (slides_dir, cache, clips_dir):
        d.mkdir(parents=True, exist_ok=True)
    subprocess.run(["pdftoppm", "-png", "-r", "96", "-scale-to-x", "1920", "-scale-to-y", "1080",
                    str(pdf), str(slides_dir / "slide")], check=True)
    slides = sorted(slides_dir.glob("slide-*.png"))
    if len(slides) != len(script):
        raise SystemExit(f"{len(slides)} slides but {len(script)} chapters in script.md")

    clips = []
    for i, ((name, text), slide) in enumerate(zip(script, slides), 1):
        audio = voice(text, cache)
        length = LEAD + duration(audio) + TAIL
        clip = clips_dir / f"{i:02d}-{name}.mp4"
        subprocess.run([
            "ffmpeg", "-y", "-loglevel", "error",
            "-loop", "1", "-framerate", "30", "-i", str(slide), "-i", str(audio),
            "-filter_complex",
            f"[0:v]fade=in:d={FADE},fade=out:st={length - FADE:.3f}:d={FADE},format=yuv420p[v];"
            f"[1:a]adelay={int(LEAD * 1000)}:all=1,apad,atrim=0:{length:.3f},"
            "aformat=sample_rates=48000:channel_layouts=stereo[a]",
            "-map", "[v]", "-map", "[a]", "-t", f"{length:.3f}",
            "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-tune", "stillimage",
            "-c:a", "aac", "-b:a", "192k", str(clip),
        ], check=True)
        clips.append(clip)
        print(f"{i:02d} {name:12s} {length:5.1f}s")

    listing = clips_dir / "clips.txt"
    listing.write_text("".join(f"file '{c.name}'\n" for c in clips), encoding="utf-8")
    # Web-level loudness (-16 LUFS) for the whole film, video stream copied as is.
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0",
                    "-i", str(listing), "-c:v", "copy", "-af", "loudnorm=I=-16:TP=-1.5:LRA=11",
                    "-ar", "48000", "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", str(out)],
                   check=True)
    print(f"wrote {out} ({duration(out):.0f}s)")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pdf", type=Path, default=WORK / "operator-demo-deck.pdf")
    parser.add_argument("--out", type=Path, default=WORK / "operator-demo.mp4")
    args = parser.parse_args(argv)
    render(args.pdf, args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
