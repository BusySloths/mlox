from __future__ import annotations

from types import SimpleNamespace

from mlox.application import ProjectApplication


def test_from_session_exposes_project_and_secrets():
    session = SimpleNamespace(
        project=SimpleNamespace(name="demo"),
        secrets=object(),
    )

    application = ProjectApplication.from_session(session)

    assert application.project.name == "demo"
    assert application.secrets is session.secrets


def test_project_created_returns_project_payload():
    session = SimpleNamespace(
        project=SimpleNamespace(name="demo"),
        secrets=object(),
    )

    result = ProjectApplication.from_session(session).project_created()

    assert result.success
    assert result.data == {"project": session.project}
