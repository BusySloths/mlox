from __future__ import annotations

from mlox.project import ProjectWorkspace
from mlox.project.entries import Entry


def test_workspace_exposes_flattened_state(tmp_path):
    workspace = ProjectWorkspace.create(str(tmp_path / "demo"), "pw")
    assert workspace.name == "demo"
    assert workspace.infrastructure.bundles == []
    assert workspace.secrets.is_working()


def test_project_created_returns_workspace_payload(tmp_path):
    workspace = ProjectWorkspace.create(str(tmp_path / "demo"), "pw")
    result = workspace.project_created()

    assert result.success
    assert result.data == {"workspace": workspace}


def test_workspace_entry_pass_throughs_round_trip(tmp_path):
    workspace = ProjectWorkspace.create(str(tmp_path / "demo"), "pw")

    saved = workspace.save_entry(Entry(kind="board", title="Board", body_md="## Open\n"))
    assert saved.id

    assert workspace.list_entries() == [saved]
    assert workspace.list_entries(kind="note") == []
    assert workspace.get_entry(saved.id) == saved
    assert workspace.find_entry_by_title("board") == saved

    saved.body_md = "## Open\n\n- [ ] first\n"
    workspace.save_entry(saved)
    assert workspace.get_entry(saved.id).body_md.endswith("- [ ] first\n")

    workspace.delete_entry(saved.id)
    assert workspace.get_entry(saved.id) is None
    assert workspace.list_entries() == []
