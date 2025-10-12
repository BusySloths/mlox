import json
import pytest

from mlox.secret_manager import TinySecretManager
from mlox.utils import dataclass_to_dict

pytestmark = pytest.mark.integration


def test_secret_roundtrip(ubuntu_docker_server):
    password = "integration-test"
    server_dict = dataclass_to_dict(ubuntu_docker_server)
    sm = TinySecretManager("", ".secrets", password, server_dict=server_dict)

    assert sm.is_working()

    secret_name = "ITEST_SECRET"
    secret_payload = {"alpha": 1, "beta": "value"}

    sm.save_secret(secret_name, secret_payload)
    assert sm.load_secret(secret_name) == secret_payload

    listed = sm.list_secrets(use_cache=False)
    assert secret_name in listed and listed[secret_name] == secret_payload

    keys_only = sm.list_secrets(keys_only=True, use_cache=False)
    assert secret_name in keys_only and keys_only[secret_name] is None

    with ubuntu_docker_server.get_server_connection() as conn:
        file_path = f"{sm.path}/{secret_name}.json"
        executor = ubuntu_docker_server.exec
        raw_contents = executor.fs_read_file(
            conn, file_path, encoding="utf-8", format="json"
        )
        with pytest.raises(json.JSONDecodeError):
            json.loads(raw_contents)
        executor.run_filesystem_task(conn, f"rm -f {file_path}")
