from __future__ import annotations

import pytest

from scripts.content_pipeline.redact import (
    DEFAULT_IP_PREFIX,
    DEFAULT_LITERALS,
    DEFAULT_PREFIXES,
    Patch,
    build_filter_chain,
    classify_word,
    cluster_patches,
    propagate_persistent,
    scene_pairs,
)


def test_classify_ip_maps_into_documentation_range():
    ips: dict[str, str] = {}
    first = classify_word("10.44.165.102", ip_map=ips)
    second = classify_word("10.44.91.16", ip_map=ips)
    assert first == "198.51.100.10"
    assert second == "198.51.100.20"
    # stable per address within a run, so a server keeps its fake IP
    assert classify_word("(10.44.165.102)", ip_map=ips) == "(198.51.100.10)"
    assert classify_word("not.an.ip") is None


def test_classify_ip_never_keeps_any_part_of_the_real_address():
    for real in ("194.163.165.102", "161.97.91.16", "192.168.0.1"):
        fake = classify_word(real)
        assert fake.startswith("198.51.100.")
        assert fake.rsplit(".", 1)[1] != real.rsplit(".", 1)[1]


def test_fake_ip_octets_stay_valid_for_many_addresses():
    ips: dict[str, str] = {}
    fakes = [classify_word(f"10.0.{i // 250}.{i % 250}", ip_map=ips) for i in range(300)]
    octets = [int(f.rsplit(".", 1)[1]) for f in fakes]
    assert all(1 <= o <= 254 for o in octets)
    assert len(set(fakes[:24])) == 24  # first two dozen servers all distinct


def test_classify_literals_chain():
    assert (
        classify_word("tootflow-git-nicococo/") == "demoflow-git-demo/"
    )
    assert classify_word("ooitflow-postgres") == "demoflow-postgres"
    assert classify_word("clean-service") is None


def test_classify_prefix_rules():
    assert classify_word("airtime-event-recommender/") == "demo-event-recommender"
    assert classify_word("airtime-recommender") == "demo-recommender"
    assert classify_word("airtime-ml") == "demo-ml"


def test_classify_with_custom_rules():
    repl = classify_word(
        "myclient", literals={"myclient": "demo"}, prefixes={"airtime": "x"}
    )
    assert repl == "demo"


def test_cluster_patches_majority_vote_beats_single_misread():
    detections = [
        Patch(x=132, y=416, w=59, h=14, replacement="198.51.100.142", windows={(0, 5)}),
        Patch(x=132, y=416, w=59, h=14, replacement="198.51.100.142", windows={(5, 11)}),
        Patch(x=133, y=417, w=59, h=14, replacement="198.51.100.162", windows={(11, 15)}),
    ]
    patches = cluster_patches(detections)
    assert len(patches) == 1
    assert patches[0].replacement == "198.51.100.142"
    # adjacent windows merge into one contiguous coverage run
    assert patches[0].windows == {(0, 15)}


def test_propagate_persistent_extends_sidebar_entities():
    scenes = [(0, 5), (5, 11), (11, 15)]
    sidebar = Patch(x=100, y=416, w=59, h=14, replacement="x", windows={(11, 15)})
    content = Patch(x=500, y=200, w=59, h=14, replacement="y", windows={(11, 15)})
    propagate_persistent([sidebar, content], scenes, tui_start=5.0)
    assert sidebar.windows == {(5, 11), (11, 15)}
    assert content.windows == {(11, 15)}


def test_build_filter_chain_enables_box_and_text_per_window():
    import re

    patch = Patch(x=10, y=20, w=90, h=14, replacement="198.51.100.142",
                  bg="0x042527", windows={(5, 11), (11, 15)})
    chain = build_filter_chain([patch])
    assert len(re.findall(r"drawbox=", chain)) == 2
    assert len(re.findall(r"drawtext=", chain)) == 2
    assert "enable='between(t,5,11)'" in chain
    assert "enable='between(t,11,15)'" in chain
    assert "fontsize=13" in chain
    assert "198.51.100.142" in chain


def test_scene_pairs_covers_full_duration():
    pairs = scene_pairs([5.0, 11.0], 15.0)
    assert pairs == [(0.0, 5.0), (5.0, 11.0), (11.0, 15.0)]


def test_default_font_prefers_env_override(tmp_path, monkeypatch):
    from scripts.content_pipeline.redact import default_font

    font = tmp_path / "Custom.ttf"
    font.write_bytes(b"")
    monkeypatch.setenv("MLOX_CONTENT_FONT", str(font))
    assert default_font() == str(font)


def test_default_font_falls_back_to_first_existing_candidate(tmp_path, monkeypatch):
    from scripts.content_pipeline import redact

    present = tmp_path / "Menlo.ttc"
    present.write_bytes(b"")
    monkeypatch.delenv("MLOX_CONTENT_FONT", raising=False)
    monkeypatch.setattr(
        redact, "FONT_CANDIDATES", (str(tmp_path / "missing.ttf"), str(present)))
    assert redact.default_font() == str(present)


def test_default_font_raises_when_no_font_exists(tmp_path, monkeypatch):
    from scripts.content_pipeline import redact

    monkeypatch.delenv("MLOX_CONTENT_FONT", raising=False)
    monkeypatch.setattr(redact, "FONT_CANDIDATES", (str(tmp_path / "missing.ttf"),))
    with pytest.raises(FileNotFoundError, match="MLOX_CONTENT_FONT"):
        redact.default_font()


def test_build_filter_chain_escapes_drawtext_specials(tmp_path):
    font = tmp_path / "f.ttf"
    font.write_bytes(b"")
    patch = Patch(x=1, y=2, w=90, h=14, replacement="it's me@host:~ 100%",
                  windows={(0, 1)})
    chain = build_filter_chain([patch], font_path=str(font))
    assert "text='it\u2019s me@host\\:~ 100%'" in chain
    assert ":expansion=none:" in chain


def test_match_entity_finds_contained_and_truncated_entities():
    from scripts.content_pipeline.redact import match_entity

    known = ["acme-sw-ag", "10.44.171.73", "demouser"]
    assert match_entity("Github:git@github.com:acme-sw-ag/x.git", known) == "acme-sw-ag"
    assert match_entity("acme-sw-", known) == "acme-sw-ag"  # cut off by a column
    assert match_entity("(10.44.171.73)", known) == "10.44.171.73"
    assert match_entity("10.44.17", known) == "10.44.171.73"
    assert match_entity("DEMOUSER", known) == "demouser"
    assert match_entity("acm", known) is None  # too short to be a prefix hit
    assert match_entity("docker", known) is None
    assert match_entity("anything", []) is None


def test_scene_window_returns_enclosing_scene():
    from scripts.content_pipeline.redact import scene_window

    scenes = [(0.0, 4.0), (4.0, 9.5), (9.5, 12.0)]
    assert scene_window(5.0, scenes) == (4.0, 9.5)
    assert scene_window(12.0, scenes) == (9.5, 12.0)
    assert scene_window(20.0, scenes) is None


def _two_window_patch():
    return Patch(x=100, y=50, w=80, h=14, replacement="x",
                 windows={(1.0, 2.0), (5.0, 6.5)})


def test_box_style_fills_padded_black_box_once_per_patch():
    chain = build_filter_chain([_two_window_patch()], style="box")
    assert chain.count("drawbox=") == 1
    assert "drawtext" not in chain
    assert "color=black" in chain
    assert "enable='between(t,1.0,2.0)+between(t,5.0,6.5)'" in chain
    # padded beyond the OCR box on every side
    assert "x=93:" in chain and "y=46:" in chain


def test_blur_style_merges_one_blur_through_a_timed_box_mask():
    p1 = _two_window_patch()
    p2 = Patch(x=10, y=10, w=40, h=12, replacement="y", windows={(0.0, 1.0)})
    chain = build_filter_chain([p1, p2], style="blur")
    # one blur and one merge regardless of patch count (no per-patch branches)
    assert chain.count("gblur=") == 1
    assert chain.count("maskedmerge") == 1
    assert chain.count("split") == 1
    assert chain.count("color=white:t=fill") == 2
    assert "enable='between(t,1.0,2.0)+between(t,5.0,6.5)'" in chain
    assert "drawtext" not in chain
    assert chain.endswith("format=yuv420p")


def test_unknown_style_is_rejected():
    with pytest.raises(ValueError, match="style"):
        build_filter_chain([_two_window_patch()], style="sparkle")


def test_style_roundtrips_through_redaction_json(tmp_path):
    import json

    from scripts.content_pipeline.redact import load_style

    assert load_style(tmp_path) == "replace"  # no file: legacy behaviour
    (tmp_path / "redaction.json").write_text(
        json.dumps({"originals": [], "patches": [], "style": "blur"}))
    assert load_style(tmp_path) == "blur"


def test_match_entity_accepts_ocr_fragments_of_entities():
    from scripts.content_pipeline.redact import match_entity

    known = ["10.44.91.15", "10.44.91.16", "tootflow"]
    # misread tail of a split IP ("91.15" read as "97.15")
    assert match_entity("97.15", known) in ("10.44.91.15", "10.44.91.16")
    assert match_entity("3.8.1", known) is None  # version numbers stay readable
    assert match_entity("110.44.91.", known) in ("10.44.91.15", "10.44.91.16")
    assert match_entity("flow", known) is None  # 4 chars: too generic
    assert match_entity("mlflow-gateway", known) is None


def _tsv(*rows):
    header = ("level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\t"
              "left\ttop\twidth\theight\tconf\ttext")
    return "\n".join([header, *("\t".join(map(str, r)) for r in rows)])


def test_scan_tsv_ignores_confidence_for_entities_and_spans_ip_fragments():
    from scripts.content_pipeline.redact import scan_tsv

    # "10.44.91.15" read as three low-confidence fragments, then a table border
    tsv = _tsv(
        (5, 1, 1, 1, 1, 1, 2136, 1542, 75, 40, 40.2, "non"),
        (5, 1, 1, 1, 1, 2, 2250, 1542, 40, 40, 20.3, "97"),
        (5, 1, 1, 1, 1, 3, 2345, 1542, 90, 40, 0.0, "97.15"),
        (5, 1, 1, 1, 1, 4, 2440, 1542, 9, 40, 61.0, "|"),
        (5, 1, 1, 1, 1, 5, 2530, 1542, 110, 40, 90.0, "docker"),
    )
    hits = scan_tsv(tsv, upscale=3, known=["10.44.91.15"], classify=lambda w: None)
    assert len(hits) == 1
    original, replacement, (x, y, w, h) = hits[0]
    assert original == "10.44.91.15"
    assert (x, y) == (712, 514)
    assert x + w == (2345 + 90) // 3  # ends at the last fragment, not the border


def test_scan_tsv_keeps_confidence_threshold_for_rule_matches():
    from scripts.content_pipeline.redact import scan_tsv

    tsv = _tsv((5, 1, 1, 1, 1, 1, 30, 30, 60, 30, 12.0, "nicococo"))
    classify = lambda w: "demo" if "nicococo" in w else None  # noqa: E731
    assert scan_tsv(tsv, upscale=3, known=[], classify=classify, min_conf=40) == []
    hits = scan_tsv(tsv, upscale=3, known=[], classify=classify, min_conf=10)
    assert hits[0][:2] == ("nicococo", "demo")


def test_refine_patches_leaks_until_clean(tmp_path, monkeypatch):
    import json

    from scripts.content_pipeline import redact

    (tmp_path / "redaction.json").write_text(json.dumps(
        {"style": "blur", "originals": ["10.44.91.15"], "patches": []}))
    applied, searched = [], []
    rounds = iter([
        ([Patch(x=1, y=2, w=30, h=12, replacement="redacted", windows={(0, 4)})],
         {"10.44.91.15"}),
        ([], set()),
    ])
    monkeypatch.setattr(redact, "apply", lambda video, wd: applied.append(video) or wd / "r.mp4")

    def fake_scan(video, frames_dir, *, known, classify, **kw):
        searched.append(known)
        assert classify("198.51.100.15") is None  # replacements never re-trigger
        return next(rounds)

    monkeypatch.setattr(redact, "_scan_video", fake_scan)
    monkeypatch.setattr(redact, "bridge_static_gaps", lambda video, patches, **kw: None)
    added = redact.refine("in.mp4", tmp_path, entities=["acme-sw-ag"], rounds=3)
    assert added == 1
    assert len(applied) == 2  # apply → leak found → apply → clean
    assert searched[0] == ["10.44.91.15", "acme-sw-ag"]
    assert len(json.loads((tmp_path / "redaction.json").read_text())["patches"]) == 1


def test_bridge_windows_fills_gaps_where_region_is_unchanged():
    import numpy as np

    from scripts.content_pipeline.redact import bridge_windows

    text = np.tile(np.array([[30, 200]], dtype=np.uint8), (4, 5))  # glyph-like texture
    blank = np.zeros((4, 10), dtype=np.uint8)
    # region shows the same text at t=0..5, blank at 6, text again at 7..9
    samples = [(float(t), blank if t == 6 else text) for t in range(10)]
    windows = {(0.0, 1.5), (3.0, 4.0), (8.0, 9.0)}
    bridged = bridge_windows(windows, samples, duration=9.5)
    # 1.5→3.0 bridged (unchanged); 4.0→8.0 not (blank at 6); tail to the end
    assert (1.5, 3.0) in bridged
    assert not any(s < 6.0 < e for s, e in bridged)  # stops at the blank frame
    assert (9.0, 9.5) in bridged


def test_bridge_windows_leaves_windows_without_reference_untouched():
    from scripts.content_pipeline.redact import bridge_windows

    assert bridge_windows({(1.0, 2.0)}, [], duration=5.0) == {(1.0, 2.0)}


def test_bridge_windows_extends_partially_into_a_changing_gap():
    import numpy as np

    from scripts.content_pipeline.redact import bridge_windows

    text = np.tile(np.array([[30, 200]], dtype=np.uint8), (4, 5))
    other = np.tile(np.array([[200, 30]], dtype=np.uint8), (4, 5))
    # another tab until t=17, then the same table row appears from t=17.75 on
    samples = [(t / 4, other if t / 4 < 17.5 else text) for t in range(0, 4 * 25)]
    bridged = bridge_windows({(18.5, 22.0)}, samples, duration=25.0)
    start = min(s for s, _ in bridged)
    # pulled back to the last sample before the row appeared, no further
    assert start == 17.25


def test_bridge_windows_never_spreads_through_empty_regions():
    import numpy as np

    from scripts.content_pipeline.redact import bridge_windows

    text = np.tile(np.array([[30, 200]], dtype=np.uint8), (4, 5))
    empty = np.full((4, 10), 25, dtype=np.uint8)
    # the scene window starts before the list loaded (empty), text from t=3
    samples = [(float(t), empty if t < 3 or t > 5 else text) for t in range(12)]
    bridged = bridge_windows({(2.0, 5.5)}, samples, duration=12.0)
    # empty background elsewhere must not count as "the same text"
    assert max(e for _, e in bridged) <= 6.0
    assert min(s for s, _ in bridged) >= 1.0


def test_scan_tsv_ip_span_does_not_swallow_neighbouring_columns():
    from scripts.content_pipeline.redact import scan_tsv

    # "10.44.165.102 otel 15.5% 7.4%" in a tightly packed monitor table
    tsv = _tsv(
        (5, 1, 1, 1, 1, 1, 1000, 900, 330, 40, 90.0, "10.44.165.102"),
        (5, 1, 1, 1, 1, 2, 1360, 900, 120, 40, 90.0, "15.5%"),
        (5, 1, 1, 1, 1, 3, 1500, 900, 90, 40, 90.0, "7.4%"),
    )
    hits = scan_tsv(tsv, upscale=3, known=["10.44.165.102"], classify=lambda w: None)
    assert len(hits) == 1
    _, _, (x, y, w, h) = hits[0]
    assert x + w == (1000 + 330) // 3
