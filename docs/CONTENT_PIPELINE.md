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
| Normalized working video, transcript, timeline, redaction map, frames | `content/.work/<slug>/` | No |
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
3. Record natively with the clearest available capture tool. High-resolution
   macOS/Retina recordings are supported; keep the source aspect ratio and use
   30 fps, H.264/yuv420p where available, and 48 kHz audio. Use a disposable
   demo project and do not put real identities, credentials, or server
   addresses on screen.
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

# 2. Create a local working master. It preserves aspect ratio and uses the
#    registry limits (default: at most 1920x1440; 3000x2000 becomes 1920x1280).
uv run python -m scripts.content_pipeline normalize content/recordings/<slug>.mp4 --slug <slug>

# All remaining visual stages use the normalized working master.
WORKING=content/.work/<slug>/normalized.mp4

# 3. Create transcript.json and captions.srt; chapter markers are approximate.
uv run python -m scripts.content_pipeline transcribe "$WORKING" --slug <slug>

# 4. Until automated visual alignment exists, review frames and create this
#    local timeline by hand. Do not estimate chapter bounds from memory.
# content/.work/<slug>/timeline.json
# {"chapters":[{"name":"intro","start":0,"end":42}]}

# 5. Collect the project's ground-truth sensitive strings (IPs, git owners,
#    hostnames, emails) through the mlox CLI. The password is read from
#    MLOX_PROJECT_PASSWORD_<NAME> (or MLOX_PROJECT_PASSWORD) and never put on argv.
uv run python -m scripts.content_pipeline entities --slug <slug> --project <name>.mlox

# 6. Detect possible sensitive text, inspect redaction.json, then apply it.
#    --style blur (default) | box | replace; --refine N re-OCRs the result.
uv run python -m scripts.content_pipeline redact "$WORKING" --slug <slug>

# Re-run with --yes only after reviewing the mapping.
uv run python -m scripts.content_pipeline redact "$WORKING" --slug <slug> --yes

# 7. Make screenshots and one GIF from explicit, reviewed timestamps.
uv run python -m scripts.content_pipeline cut "$WORKING" \
  --slug <slug> --shots 12 48 --gif 54 66 --out /tmp/<slug>-artifacts

# 8. Check every final visual artifact before committing or publishing.
uv run python -m scripts.content_pipeline verify /tmp/<slug>-artifacts/*.png \
  /tmp/<slug>-artifacts/demo.gif --slug <slug>

# 9. Render an article when the piece declares an article output.
uv run python -m scripts.content_pipeline render --slug <slug> \
  --script content/<slug>/script.md
```

The `cut` command currently uses generic temporary filenames (`demo.gif` and
`shot-<seconds>s.png`). Review the files, rename them to the corresponding
`outputs[].dest` names in the registry, and copy them there before committing.
Keep GIFs at or below 15 seconds, 12 fps, and 960 px wide. The helper function
for MP4 clips exists, but clip creation is not yet exposed by the CLI.

The normalization limits are in `defaults.video` in `content/registry.yaml`.
They preserve aspect ratio and make dimensions even for yuv420p. Do not use the
normalized copy as a replacement for the local source master; regenerate it
when changing the working profile.

## Redaction and publishing gate

Detection OCRs the working master at 3x scale, once per second and right after
every scene change. A word is sensitive when a registry rule classifies it
(`redact.literals` / `redact.prefixes`, any IPv4 address) or when it shows one
of the project entities from `entities.json`, including truncated or misread
fragments such as an IP split into `97` and `97.15`. Because TUI content is
static within a scene, each detection covers its whole scene, and a patch
extends into neighbouring frames for as long as its region still shows the
same pixels (it never spreads through empty background).

Three styles are available and recorded in `redaction.json`:

- `blur` (default): one blurred copy of the frame merged through a timed mask.
- `box`: solid black boxes.
- `replace`: fake replacement text. IPs become documentation-range addresses
  (`198.51.100.10`, `.20`, …) that keep no part of the real address; each
  address keeps the same fake for the whole run.

`--refine N` (default 2) applies the redaction, OCRs the result and patches
whatever is still readable, up to N rounds. Manual patches (for example a
whole panel showing a private repository tree) can be added to
`redaction.json` as rows with explicit `windows`; refine and apply keep them.

Treat OCR detection as a candidate generator, not proof that a recording is
safe: review `content/.work/<slug>/redaction.json` and the output frames
yourself. For text you control at the source (for example CLI output), prefer
rewriting it before it reaches the screen and run `verify` on the result.

`verify` is a required visual release gate: a non-zero exit means do not
publish. It OCRs the supplied final visual files at 3x scale once per second
and fails on any detected original or project entity. Re-run it on every
re-encoded copy (different scales can make blurred text legible again). It
reads the source transcript for narration checks rather than re-transcribing
each final clip, so manually review audio in published videos as well.

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
