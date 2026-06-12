from __future__ import annotations

from mlox.project import ProjectWorkspace


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
