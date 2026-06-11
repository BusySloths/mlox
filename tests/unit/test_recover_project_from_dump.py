from __future__ import annotations

from mlox.utils import dict_to_dataclass, load_from_json
from scripts.recover_project_from_dump import _LegacyProjectDump, recover_project


def test_recover_project_writes_encrypted_project_file(tmp_path, monkeypatch):
    dump = (
        "MloxProject("
        "name='broken_project', "
        "descr='', "
        "version='0.1.0', "
        "created_at='2025-09-17T13:50:18.734286+00:00', "
        "last_opened_at='2026-03-27T15:32:59.611629+00:00', "
        "secret_manager_class='mlox.secret_manager.TinySecretManager', "
        "secret_manager_info={'secrets_master_token': 'topsecret', 'keyfile': {'ip': '127.0.0.1', 'service_config_id': 'ubuntu-docker-24.04-server', 'backend': ['docker']}}"
        ")"
    )
    dump_path = tmp_path / "mlox_project_content.key"
    dump_path.write_text(dump, encoding="utf-8")

    output_path = recover_project(
        dump_path,
        project_name="restored_project",
        password="Recovered12345",
    )

    monkeypatch.chdir(tmp_path)
    restored = dict_to_dataclass(
        load_from_json("/restored_project.project", "Recovered12345", encrypted=True),
        [_LegacyProjectDump],
    )

    assert output_path == tmp_path / "restored_project.project"
    assert restored.name == "restored_project"
    assert restored.secret_manager_class == "mlox.secret_manager.TinySecretManager"
    assert restored.secret_manager_info["secrets_master_token"] == "topsecret"
    assert (
        restored.secret_manager_info["keyfile"]["_module_name_"]
        == "mlox.servers.ubuntu.docker"
    )
    assert (
        restored.secret_manager_info["keyfile"]["_class_name_"]
        == "UbuntuDockerServer"
    )
