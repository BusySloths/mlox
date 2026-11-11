"""Align stage: map the script's chapters/steps to recording timestamps.

Placeholder for the GLM video-native pass: it watches the recording,
finds the spoken `chapter:` markers, verifies each scripted step against
the actual screen content, and emits `timeline.json`:

    {"chapters": [{"name": "install", "start": "00:00:12", "end": "00:01:04",
                   "steps": [{"text": "...", "at": "00:00:20"}]}]}

Until this stage is built, write timeline.json by hand (it is an input to
cut/render, and manual editing is a supported workflow) or run cut with
explicit time ranges.
"""


def align(video: str, script_path: str, out: str) -> dict:
    raise NotImplementedError(
        "The GLM alignment pass is not built yet; write timeline.json by "
        "hand or use explicit time ranges."
    )
