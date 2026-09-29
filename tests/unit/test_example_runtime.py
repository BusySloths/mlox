"""Examples must support independent optional runtime providers."""
import logging
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from examples import runtime


@pytest.fixture(autouse=True)
def clean_environment(monkeypatch):
    for key in list(runtime.os.environ):
        if key.startswith(("MLOX_", "OTEL_", "MLFLOW_")):
            monkeypatch.delenv(key)
    monkeypatch.setattr(runtime, "set_telemetry_client", Mock())


@pytest.mark.parametrize("telemetry,manager", [(False, False), (True, False), (False, True), (True, True)])
@pytest.mark.parametrize("source", ["environment", "project"])
def test_provider_combinations(monkeypatch, caplog, telemetry, manager, source):
    caplog.set_level(logging.INFO)
    telemetry_env = {"OTEL_EXPORTER_OTLP_ENDPOINT": "http://localhost:4317"}
    manager_env = {runtime.SECRET_MANAGER_KEYFILE_ENV: "private-key",
                   runtime.SECRET_MANAGER_KEYFILE_PW_ENV: "private-password"}
    client, secret_client = Mock(), Mock()
    monkeypatch.setattr(runtime.OTelClient, "from_env", lambda **kw: client if telemetry else None)
    loader = Mock(return_value=secret_client)
    monkeypatch.setattr(runtime, "load_secret_manager_from_env", loader)
    if source == "environment":
        for key, value in {**(telemetry_env if telemetry else {}), **(manager_env if manager else {})}.items():
            monkeypatch.setenv(key, value)
    else:
        services = []
        for enabled, capability, method, environment in (
            (telemetry, runtime.AbstractObservabilityService, "get_telemetry_env_binding", telemetry_env),
            (manager, runtime.AbstractSecretManagerService, "get_secret_manager_env_binding", manager_env),
        ):
            if enabled:
                provider = Mock(spec=capability)
                provider.state, provider.name, provider.service_uuid = "running", "provider", "uuid"
                getattr(provider, method).return_value = environment
                services.append(provider)
        workspace = SimpleNamespace(infrastructure=SimpleNamespace(bundles=[SimpleNamespace(services=services)]))
        monkeypatch.setenv("MLOX_PROJECT_PATH", "project")
        monkeypatch.setenv("MLOX_PROJECT_PASSWORD", "password")
        monkeypatch.setattr("examples.load_project_data.load_project_workspace", lambda: workspace)
    actual = runtime.setup_runtime()
    assert actual == (client if telemetry else None, secret_client if manager else None)
    assert loader.call_count == int(manager)
    assert f"telemetry={telemetry}, secret_manager={manager}" in caplog.text
    assert "private-key" not in caplog.text
    assert "private-password" not in caplog.text


def test_local_tracking_default(monkeypatch):
    monkeypatch.setattr(runtime.OTelClient, "from_env", lambda **kw: None)
    runtime.setup_runtime(tracking=True)
    assert runtime.os.environ["MLFLOW_URI"] == "sqlite:///mlox-example-mlflow.db"


def test_incomplete_secret_manager_fails(monkeypatch):
    monkeypatch.setenv(runtime.SECRET_MANAGER_KEYFILE_ENV, "private-key")
    with pytest.raises(ValueError, match="Incomplete configuration"):
        runtime.setup_runtime()


def test_disable_existing_bindings(monkeypatch):
    for key in (runtime.SECRET_MANAGER_KEYFILE_ENV, runtime.SECRET_MANAGER_KEYFILE_PW_ENV,
                "OTEL_EXPORTER_OTLP_ENDPOINT"):
        monkeypatch.setenv(key, "configured")
    monkeypatch.setenv("MLOX_EXAMPLE_SECRET_MANAGER", "none")
    monkeypatch.setenv("MLOX_EXAMPLE_TELEMETRY", "none")
    assert runtime.setup_runtime() == (None, None)


@pytest.mark.parametrize("selection", [None, "second", "id-second"])
@pytest.mark.parametrize("kind", ["telemetry", "secret_manager", "tracker"])
def test_multiple_providers_select_first_or_override(monkeypatch, caplog, selection, kind):
    caplog.set_level(logging.INFO)
    capability = {"telemetry": runtime.AbstractObservabilityService,
                  "secret_manager": runtime.AbstractSecretManagerService}.get(kind)
    providers = []
    for name in ("first", "second"):
        provider = Mock(spec=capability) if capability else Mock()
        provider.name, provider.service_uuid, provider.state = name, f"id-{name}", "running"
        if kind == "telemetry":
            provider.get_telemetry_env_binding.return_value = {}
        elif kind == "secret_manager":
            provider.get_secret_manager_env_binding.return_value = {}
        else:
            provider.get_secrets.return_value = {"service_url": f"https://{name}.example"}
        providers.append(provider)
    bundles = [SimpleNamespace(services=[p], server=SimpleNamespace(uuid=f"server-{p.name}", ip="127.0.0.1"))
               for p in providers]
    infra = SimpleNamespace(bundles=bundles, filter_by_group=lambda group: providers)
    monkeypatch.setattr("examples.load_project_data.load_project_workspace",
                        lambda: SimpleNamespace(infrastructure=infra))
    monkeypatch.setenv("MLOX_PROJECT_PATH", "project")
    monkeypatch.setenv("MLOX_PROJECT_PASSWORD", "password")
    if selection:
        monkeypatch.setenv(f"MLOX_EXAMPLE_{kind.upper()}", selection)
    monkeypatch.setattr(runtime.OTelClient, "from_env", lambda **kw: None)
    runtime.setup_runtime(tracking=kind == "tracker")
    chosen = "second" if selection else "first"
    assert f"selected {chosen} (id-{chosen}), server=server-{chosen} (127.0.0.1)" in caplog.text
    method = {"telemetry": "get_telemetry_env_binding",
              "secret_manager": "get_secret_manager_env_binding", "tracker": "get_secrets"}[kind]
    getattr(providers[1 if selection else 0], method).assert_called_once_with()
    getattr(providers[0 if selection else 1], method).assert_not_called()
