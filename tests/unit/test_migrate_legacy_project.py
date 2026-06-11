from __future__ import annotations

from mlox.infra import Infrastructure
from mlox.project.store import ProjectDatabase
from mlox.secret_manager import AbstractSecretManager
from mlox.utils import save_to_json
from scripts.migrate_legacy_project import migrate_legacy_project


class MigrationSecretManager(AbstractSecretManager):
    values = {
        "MLOX_CONFIG_INFRASTRUCTURE": Infrastructure().to_dict(),
        "TOKEN": {"value": "legacy"},
    }

    def is_working(self):
        return True

    def list_secrets(self, keys_only=False):
        return {key: None for key in self.values} if keys_only else dict(self.values)

    def save_secret(self, name, my_secret):
        self.values[name] = my_secret

    def load_secret(self, name):
        return self.values.get(name)

    @classmethod
    def instantiate_secret_manager(cls, info):
        return cls()

    def get_access_secrets(self):
        return {}


def test_migration_copies_data_without_altering_source(tmp_path):
    source = tmp_path / "legacy.project"
    payload = {
        "name": "legacy",
        "descr": "Imported project",
        "version": "0.9.0",
        "created_at": "2024-01-01T00:00:00+00:00",
        "secret_manager_class": "tests.unit.test_migrate_legacy_project.MigrationSecretManager",
        "secret_manager_info": {},
    }
    save_to_json(payload, str(source), "old-password", encrypt=True)
    original = source.read_bytes()

    output = migrate_legacy_project(
        source, tmp_path / "new-project", "old-password", "new-password"
    )

    assert source.read_bytes() == original
    store = ProjectDatabase(output, "new-password").open()
    metadata = store.load_project()
    assert metadata["name"] == "legacy"
    assert metadata["descr"] == "Imported project"
    assert metadata["version"] == "0.9.0"
    assert metadata["created_at"] == "2024-01-01T00:00:00+00:00"
    assert store.load_secret("TOKEN") == {"value": "legacy"}
    assert store.load_secret("MLOX_CONFIG_INFRASTRUCTURE") is None
    with store.connection() as conn:
        assert conn.execute("SELECT COUNT(*) FROM legacy_imports").fetchone()[0] == 1
