from __future__ import annotations

import pytest

from scripts.content_pipeline.transcribe import (
    Segment,
    extract_markers,
    srt_from_segments,
    transcribe,
    transcript_leaks,
)


def test_extract_markers_tolerant_to_stt_wording():
    segments = [
        Segment(0.0, 3.0, "Welcome to the demo."),
        Segment(3.0, 6.0, "chapter install"),  # STT drops the colon
        Segment(6.0, 9.0, "Chapter: TUI-Tour, let's look around"),
        Segment(9.0, 12.0, "chapters of the book"),  # not a marker
    ]
    assert extract_markers(segments) == [("install", 3.0), ("tui-tour", 6.0)]


def test_srt_from_segments_formats_and_skips_empty():
    segments = [
        Segment(0.0, 2.5, "Hello world"),
        Segment(2.5, 4.0, "  "),
        Segment(61.0, 63.123, "Second block"),
    ]
    srt = srt_from_segments(segments)
    blocks = [b for b in srt.split("\n\n") if b.strip()]
    assert len(blocks) == 2
    assert "00:00:00,000 --> 00:00:02,500" in srt
    assert "00:01:01,000 --> 00:01:03,123" in srt
    assert "Hello world" in srt and "Second block" in srt


def test_transcript_leaks_case_insensitive():
    segments = [Segment(0.0, 5.0, "We deploy to 194.163.165.102 today")]
    assert transcript_leaks(["194.163.165.102", "nicococo"], segments) == [
        "194.163.165.102"
    ]


def test_transcribe_uses_verbose_json_segments_when_present(tmp_path, monkeypatch):
    audio = tmp_path / "audio.ogg"
    audio.write_bytes(b"fake")

    def fake_post(api_key, path, model, language):
        return {"text": "hello", "segments": [
            {"start": 0.0, "end": 2.0, "text": " chapter intro "},
        ]}

    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    segments = transcribe(audio, api_key="k", work_dir=tmp_path,
                          post_multipart=fake_post)
    assert segments == [Segment(0.0, 2.0, "chapter intro")]


def test_transcribe_falls_back_to_chunked_mode(tmp_path, monkeypatch):
    import scripts.content_pipeline.transcribe as stt

    audio = tmp_path / "audio.ogg"
    audio.write_bytes(b"fake")

    def fake_post(api_key, path, model, language):
        # no segments -> triggers the chunked fallback
        return {"text": "chapter intro"}

    def fake_slice(audio_path, out_dir, seconds):
        out_dir.mkdir(parents=True, exist_ok=True)
        chunks = []
        for i in range(2):
            chunk = out_dir / f"chunk-{i:03d}.ogg"
            chunk.write_bytes(b"fake")
            chunks.append(chunk)
        return chunks

    monkeypatch.setattr(stt, "_slice_audio", fake_slice)
    texts = iter(["chapter intro", "chapter install"])
    monkeypatch.setattr(stt, "_transcribe_chunk",
                        lambda *a, **k: next(texts))

    segments = stt.transcribe(audio, api_key="k", chunk_seconds=30,
                              work_dir=tmp_path, post_multipart=fake_post)
    assert [(s.start, s.end, s.text) for s in segments] == [
        (0.0, 30.0, "chapter intro"),
        (30.0, 60.0, "chapter install"),
    ]


def test_transcribe_requires_api_key(tmp_path, monkeypatch):
    audio = tmp_path / "audio.ogg"
    audio.write_bytes(b"fake")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="OPENAI_API_KEY"):
        transcribe(audio)
