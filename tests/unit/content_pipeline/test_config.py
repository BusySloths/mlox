from __future__ import annotations

import pytest

from scripts.content_pipeline.config import RegistryError, load_registry


def write_registry(tmp_path, text: str):
    path = tmp_path / "registry.yaml"
    path.write_text(text)
    return load_registry(path)


def test_load_registry_valid(tmp_path):
    registry = write_registry(
        tmp_path,
        """
defaults:
  gif:
    fps: 12
pieces:
  - slug: install-to-first-service
    type: tutorial
    title: Demo
    status: draft
    outputs:
      - type: readme_gif
        dest: mlox/resources/tui-demo.gif
""",
    )
    piece = registry.piece("install-to-first-service")
    assert piece.type == "tutorial"
    assert piece.outputs[0]["dest"] == "mlox/resources/tui-demo.gif"
    assert registry.defaults["gif"]["fps"] == 12


def test_duplicate_slug_rejected(tmp_path):
    with pytest.raises(RegistryError, match="Duplicate"):
        write_registry(
            tmp_path,
            """
pieces:
  - slug: a
    type: tutorial
  - slug: a
    type: short
""",
        )


def test_unknown_type_rejected(tmp_path):
    with pytest.raises(RegistryError, match="unknown type"):
        write_registry(
            tmp_path,
            """
pieces:
  - slug: a
    type: podcast
""",
        )


def test_unknown_status_rejected(tmp_path):
    with pytest.raises(RegistryError, match="unknown status"):
        write_registry(
            tmp_path,
            """
pieces:
  - slug: a
    type: demo
    status: archived
""",
        )


def test_missing_pieces_section_rejected(tmp_path):
    with pytest.raises(RegistryError, match="pieces"):
        write_registry(tmp_path, "defaults: {}\n")
