from mlox.migrations.base import MloxMigrations, load_mlox_session


class AddFieldModelServerRegistryUUID(MloxMigrations):
    name = "add_field_model_server_registry_uuid"

    def migrate(self, data: dict) -> dict:
        new_data = self._add_field_to_class(
            data,
            module_name="mlox.services.mlflow_mlserver.docker",
            class_name="MLFlowMLServerDockerService",
            field_name="registry_uuid",
            default_value=None,
        )
        return self._migrate_childs(new_data)


if __name__ == "__main__":
    print("Loading MLOX project...")
    print(
        "Make sure MLOX_PROJECT_NAME and MLOX_PROJECT_PASSWORD environment variables are set and a project exists."
    )
    migration = AddFieldModelServerRegistryUUID()
    session = load_mlox_session([migration])
    print("Project loaded:", session.project.name)
