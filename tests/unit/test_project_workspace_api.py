from __future__ import annotations

import inspect

from mlox.project import ProjectWorkspace
from mlox.project.entries import Entry


SUPPORTED_WORKSPACE_METHOD_SIGNATURES = {
    "open": "(path, password)",
    "create": "(path, password)",
    "can_open": "(path, password)",
    "commit": "(self)",
    "reload": "(self)",
    "list_entries": "(self, kind=None)",
    "get_entry": "(self, entry_id)",
    "find_entry_by_title": "(self, title, kind=None)",
    "save_entry": "(self, entry)",
    "delete_entry": "(self, entry_id)",
    "list_secret_managers": "(self)",
    "probe_secret_manager": "(self, manager_id)",
    "set_secret_manager": "(self, service_uuid, *, migrate=True)",
    "use_embedded_secret_manager": "(self, *, migrate=True)",
    "list_servers": "(self)",
    "add_server": (
        "(self, *, template_path, ip, port, root_user, root_password, "
        "extra_params=None)"
    ),
    "setup_server": "(self, *, ip)",
    "check_server_health": "(self, *, ip)",
    "teardown_server": "(self, *, ip)",
    "save_server_key": "(self, *, ip, output_path)",
    "list_services": "(self)",
    "add_service": "(self, *, server_ip, template_id, params=None)",
    "setup_service": "(self, *, name)",
    "check_service_health": "(self, *, name)",
    "teardown_service": "(self, *, name)",
    "start_service": "(self, *, name)",
    "restart_service": "(self, *, name)",
    "stop_service": "(self, *, name)",
    "rename_service": "(self, *, name, new_name)",
    "service_logs": "(self, *, name, label=None, tail=200)",
    "list_models": "(self, *, registry_name=None)",
    "deploy_model": (
        "(self, *, registry_name, model_name, model_version, server_ip, "
        "template_id='mlflow-mlserver-3.8.1-docker')"
    ),
    "list_server_configs": "()",
    "list_service_configs": "()",
}


def _signature_without_annotations(callable_object) -> str:
    signature = inspect.signature(callable_object)
    parameters = [
        parameter.replace(annotation=inspect.Parameter.empty)
        for parameter in signature.parameters.values()
    ]
    return str(
        signature.replace(
            parameters=parameters,
            return_annotation=inspect.Signature.empty,
        )
    )


def test_supported_workspace_api_signatures_are_stable():
    actual = {
        name: _signature_without_annotations(getattr(ProjectWorkspace, name))
        for name in SUPPORTED_WORKSPACE_METHOD_SIGNATURES
    }

    assert actual == SUPPORTED_WORKSPACE_METHOD_SIGNATURES


def test_supported_workspace_api_is_documented_and_typed():
    for name in SUPPORTED_WORKSPACE_METHOD_SIGNATURES:
        method = getattr(ProjectWorkspace, name)
        signature = inspect.signature(method)

        assert inspect.getdoc(method), name
        assert signature.return_annotation is not inspect.Signature.empty, name
        for parameter in signature.parameters.values():
            if parameter.name not in {"self", "cls"}:
                assert parameter.annotation is not inspect.Parameter.empty, (
                    name,
                    parameter.name,
                )


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
