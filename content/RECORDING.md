# Recording Checklist

Follow this before every recording; the pipeline validates against it.

## Capture settings

Capture natively on the platform that produces the clearest result. The
pipeline keeps this high-resolution master local and creates a reproducible
working copy before OCR, redaction, and cutting. Do not pre-scale or crop the
source recording.

| Setting | Target |
| --- | --- |
| Resolution | Native capture; at least 1080 px high. Retina/3:2 captures are supported. |
| Encoder | H.264 or a broadly supported equivalent; use a quality-focused setting, no bitrate cap |
| FPS | 30 |
| Pixel format | yuv420p (NV12) |
| Audio | 48 kHz, AAC 192k |

For OBS, set both Base (Canvas) and Output (Scaled) resolution deliberately.
Changing only the output can silently retain a 720p canvas. macOS capture is a
supported alternative when it produces crisper terminal and UI text.

## Terminal

- Size: 120x36, fullscreen, JetBrainsMono Nerd Font, large size
- Hide the system clock and notifications

## Content discipline

- Record against a disposable demo project where possible; never rely on
  post-processing alone — the redact stage is a safety net, not a substitute
- Never show public IPs you do not want published; all IPs are redacted
  regardless (same-length documentation-range swaps)
- Speak a `chapter: <name>` marker before each chapter (the STT stage
  transcribes it via `gpt-4o-mini-transcribe` to build the timeline)
- Move the mouse slowly; leave no typos on screen
- Save as `content/recordings/<slug>.mkv` (gitignored)

## After recording

1. `uv run python -m scripts.content_pipeline ingest content/recordings/<slug>.mkv`
2. Run `normalize` to create `content/.work/<slug>/normalized.mp4`.
3. Use that normalized file for transcribe, redact (review `redaction.json`),
   cut, verify, render, and publish. See `docs/CONTENT_PIPELINE.md`.
