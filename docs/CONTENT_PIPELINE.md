# Content Pipeline Recipe

This recipe turns one reviewed script and one local recording into the media
and written content for an MLOX tutorial or demo. It is the operational guide
for the **Video / demo series** roadmap item; product direction remains in
[the Doctrine](DOCTRINE.md).

The current implementation deliberately keeps recordings and generated work
files out of Git. Commit the script, registry entry, and final publishable
artifacts only.

## What is authoritative

| Item | Location | Versioned? |
| --- | --- | --- |
| Piece metadata and output destinations | `content/registry.yaml` | Yes |
| Spoken/on-screen source script | `content/<slug>/script.md` | Yes |
| Recording | `content/recordings/<slug>.<ext>` | No |
| Transcript, timeline, redaction map, frames, redacted video | `content/.work/<slug>/` | No |
| Published screenshots, GIFs, articles | Registry `outputs[].dest` | Yes |

Do not start from an unplanned recording: write and review the script first.
Use `## Chapter: <name>` headings, bullets for on-screen actions, and `>`
blockquotes for narration. Speak `chapter: <name>` before each chapter while
recording. See the [recording checklist](../content/RECORDING.md).

## Before recording

1. Add or update the piece in `content/registry.yaml`. Give every output a
   unique destination; two pieces must not claim the same file.
2. Create `content/<slug>/script.md`, including front matter and the chapter
   structure above.
3. Record with the OBS preset in `content/RECORDING.md`: 1920×1080 canvas and
   output, 30 fps, H.264/yuv420p, and 48 kHz audio. Use a disposable demo
   project and do not put real identities, credentials, or server addresses on
   screen.
4. Save the recording as `content/recordings/<slug>.mp4` (or `.mkv`). It is
   intentionally ignored by Git.

## Process a piece

Run commands from the repository root. `transcribe` requires `OPENAI_API_KEY`;
the command loads an existing repo `.env` without overriding an environment
variable. The remaining stages use local ffmpeg, ffprobe, Tesseract, and
Python dependencies.

```bash
# 1. Validate the recording preset. Fix warnings before continuing.
uv run python -m scripts.content_pipeline ingest content/recordings/<slug>.mp4

# 2. Create transcript.json and captions.srt; chapter markers are approximate.
uv run python -m scripts.content_pipeline transcribe content/recordings/<slug>.mp4 --slug <slug>

# 3. Until automated visual alignment exists, review frames and create this
#    local timeline by hand. Do not estimate chapter bounds from memory.
# content/.work/<slug>/timeline.json
# {"chapters":[{"name":"intro","start":0,"end":42}]}

# 4. Detect possible sensitive text, inspect redaction.json, then apply it.
uv run python -m scripts.content_pipeline redact content/recordings/<slug>.mp4 --slug <slug>

# Re-run with --yes only after reviewing the mapping.
uv run python -m scripts.content_pipeline redact content/recordings/<slug>.mp4 --slug <slug> --yes

# 5. Make screenshots and one GIF from explicit, reviewed timestamps.
uv run python -m scripts.content_pipeline cut content/recordings/<slug>.mp4 \
  --slug <slug> --shots 12 48 --gif 54 66 --out /tmp/<slug>-artifacts

# 6. Check every final visual artifact before committing or publishing.
uv run python -m scripts.content_pipeline verify /tmp/<slug>-artifacts/*.png \
  /tmp/<slug>-artifacts/demo.gif --slug <slug>

# 7. Render an article when the piece declares an article output.
uv run python -m scripts.content_pipeline render --slug <slug> \
  --script content/<slug>/script.md
```

The `cut` command currently uses generic temporary filenames (`demo.gif` and
`shot-<seconds>s.png`). Review the files, rename them to the corresponding
`outputs[].dest` names in the registry, and copy them there before committing.
Keep GIFs at or below 15 seconds, 12 fps, and 960 px wide. The helper function
for MP4 clips exists, but clip creation is not yet exposed by the CLI.

## Redaction and publishing gate

Every IP address is replaced with the documentation range
`198.51.100.<last-octet>`. Names and project-specific identifiers come from the
default and per-piece `redact.literals` / `redact.prefixes` mappings in the
registry. Treat OCR detection as a candidate generator, not proof that a
recording is safe: review `content/.work/<slug>/redaction.json` and the output
frames yourself.

`verify` is a required visual release gate: a non-zero exit means do not
publish. It OCRs the supplied final visual files at higher resolution and
compares them with the entities detected during redaction. It currently reads
the source transcript for narration checks rather than re-transcribing each
final clip, so manually review audio in published videos as well.

## Current limitations and follow-up work

- `align` is a placeholder. Hand-authored `timeline.json` is the supported
  workflow until visual alignment is implemented.
- Outputs are not yet materialized directly from registry destinations, and
  destination collisions are not rejected automatically.
- Article rendering currently renders the script body; timeline chapter data is
  not passed through by the CLI.
- The automated verifier cannot prove absence of an entity that OCR missed.

Record these limitations in reviews and resolve them before treating the
pipeline as fully hands-off. The implementation work is tracked in the content
pipeline issue and its linked pull request.
