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
    assert classify_word("194.163.165.102") == "198.51.100.102"
    assert classify_word("161.97.91.16") == "198.51.100.16"
    assert classify_word("192.168.0.1") == "198.51.100.1"
    assert classify_word("not.an.ip") is None


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
    assert patches[0].windows == {(0, 5), (5, 11), (11, 15)}


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
