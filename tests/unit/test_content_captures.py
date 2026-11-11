import json
from types import SimpleNamespace

import pytest

from content.scripts import ansi2html, capture, captures


def test_capture_saves_only_changed_pane_frames(tmp_path, monkeypatch):
    times = iter([0, 0, 0, 0, 1, 1, 2, 3])
    monkeypatch.setattr(capture.time, "monotonic", lambda: next(times))
    monkeypatch.setattr(capture.time, "sleep", lambda _: None)
    monkeypatch.setattr(capture.subprocess, "run", lambda *a, **k: SimpleNamespace(stdout=b"hello", returncode=0))
    capture.capture(["w1:p1"], tmp_path, duration=2, interval=1)
    assert len(list(tmp_path.glob("*.ansi"))) == 1
    assert len((tmp_path / "frames.jsonl").read_text().splitlines()) == 1


def test_capture_ignores_clock_ticks_and_skips_unreadable_panes(tmp_path, monkeypatch):
    outputs = iter([
        SimpleNamespace(stdout=b"12:00:01 ok", returncode=0),
        SimpleNamespace(stdout=b"", stderr=b"busy", returncode=1),
        SimpleNamespace(stdout=b"12:00:05 ok", returncode=0),
        SimpleNamespace(stdout=b"12:00:07 changed", returncode=0),
    ])

    def run(*args, **kwargs):
        try:
            return next(outputs)
        except StopIteration:
            raise KeyboardInterrupt  # end capture once every output was read

    monkeypatch.setattr(capture.time, "monotonic", lambda: 0)
    monkeypatch.setattr(capture.time, "sleep", lambda _: None)
    monkeypatch.setattr(capture.subprocess, "run", run)
    with pytest.raises(KeyboardInterrupt):
        capture.capture(["w1:p1"], tmp_path, duration=5, interval=1)
    frames = sorted(tmp_path.glob("*.ansi"))
    assert [f.read_bytes() for f in frames] == [b"12:00:01 ok", b"12:00:07 changed"]


def test_capture_render_redacts_before_cropping_and_escapes_html(tmp_path):
    (tmp_path / "frame.ansi").write_text("\x1b[31mprivate <&>\x1b[0m\nsecond")
    manifest = tmp_path / "selection.json"
    manifest.write_text(json.dumps({"setup": {"frame": "frame.ansi", "rows": "0:1"}}))
    mapping = tmp_path / "map.json"
    mapping.write_text(json.dumps({"private": "example"}))
    paths = captures.build(manifest, tmp_path, tmp_path / "out", mapping)
    html = paths[0].read_text()
    assert "private" not in html
    assert "example &lt;&amp;&gt;" in html
    assert "rgb(205,49,49)" in html
    assert "second" not in html


def test_capture_render_rejects_leftover_original(tmp_path):
    (tmp_path / "frame.ansi").write_text("secret")
    manifest = tmp_path / "selection.json"
    manifest.write_text(json.dumps({"setup": {"frame": "frame.ansi"}}))
    mapping = tmp_path / "map.json"
    mapping.write_text(json.dumps({"secret": "secret"}))
    with pytest.raises(ValueError, match="Original text remains"):
        captures.build(manifest, tmp_path, tmp_path / "out", mapping)
    assert not (tmp_path / "out").exists()


def test_redaction_preserves_row_width():
    rows = ansi2html.parse("│ private  │")
    redacted = ansi2html.redact(rows, {"private": "demo"})
    assert len(redacted[0]) == len(rows[0])
    assert "".join(c for c, _ in redacted[0]) == "│ demo     │"


def test_redaction_keeps_ascii_table_columns():
    rows = ansi2html.parse("| 194.163.165.102 | sartre |")
    redacted = ansi2html.redact(rows, {"194.163.165.102": "198.51.100.10"})
    assert "".join(c for c, _ in redacted[0]) == "| 198.51.100.10   | sartre |"


def test_stills_grid_and_size_follow_the_capture():
    from content.scripts import stills

    fragment = '<span style="color:red">ab&lt;</span>\n<span>cd</span>'
    assert stills.grid(fragment) == (3, 2)
    font_size, height = stills.size(cols=100, rows=10, width=624)
    assert font_size == 10
    assert height == 144


def test_stills_gif_holds_each_frame(tmp_path):
    from PIL import Image

    from content.scripts import stills

    frames = []
    for i, colour in enumerate(["red", "blue"]):
        path = tmp_path / f"{i}.png"
        Image.new("RGB", (200, 100), colour).save(path)
        frames.append((path, 0.5 + i))
    out = stills.gif(frames, tmp_path / "out.gif", width=100)
    with Image.open(out) as gif:
        assert gif.size == (100, 50)
        durations = []
        for n in range(gif.n_frames):
            gif.seek(n)
            durations.append(gif.info["duration"])
    assert durations == [500, 1500]
