from __future__ import annotations

from scripts.content_pipeline import normalize


def test_video_filter_preserves_aspect_ratio_and_makes_dimensions_even():
    assert normalize.video_filter(1920, 1440, 30) == (
        "scale=w='min(iw,1920)':h='min(ih,1440)'"
        ":force_original_aspect_ratio=decrease:force_divisible_by=2:flags=lanczos,"
        "fps=30"
    )


def test_normalize_creates_working_master_with_quality_profile(tmp_path, monkeypatch):
    commands = []

    def fake_run(command, **kwargs):
        commands.append((command, kwargs))

    monkeypatch.setattr(normalize.subprocess, "run", fake_run)
    out = tmp_path / "work" / "normalized.mp4"

    assert normalize.normalize("capture.mov", out) == out
    command, kwargs = commands[0]
    assert out.parent.is_dir()
    assert command[:7] == ["ffmpeg", "-v", "error", "-y", "-i", "capture.mov", "-map"]
    assert "-c:v" in command and command[command.index("-c:v") + 1] == "libx264"
    assert "-pix_fmt" in command and command[command.index("-pix_fmt") + 1] == "yuv420p"
    assert kwargs == {"check": True, "capture_output": True, "text": True}
