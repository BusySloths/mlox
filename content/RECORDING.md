# Recording Checklist

Follow this before every recording; the pipeline validates against it.

## OBS settings (confirmed good)

| Setting | Value |
| --- | --- |
| Base (Canvas) Resolution | 1920x1080 |
| Output (Scaled) Resolution | 1920x1080 (both fields — an output-only change silently stays 720p) |
| Encoder | x264, CRF 20 (18 for text-critical), no bitrate cap |
| FPS | 30 |
| Pixel format | yuv420p (NV12) |
| Audio | 48 kHz, AAC 192k |

## Terminal

- Size: 120x36, fullscreen, JetBrainsMono Nerd Font, large size
- Hide the system clock and notifications

## Content discipline

- Record against a disposable demo project where possible; never rely on
  post-processing alone — the redact stage is a safety net, not a substitute
- Never show public IPs you do not want published; all IPs are redacted
  regardless (same-length documentation-range swaps)
- Speak a `chapter: <name>` marker before each chapter
- Move the mouse slowly; leave no typos on screen
- Save as `content/recordings/<slug>.mkv` (gitignored)

## After recording

1. `uv run python -m scripts.content_pipeline ingest content/recordings/<slug>.mkv`
2. Walk the pipeline stages: redact (review `redaction.json` when prompted),
   cut, render, verify, publish
