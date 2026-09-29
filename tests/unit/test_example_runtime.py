"""Project examples select independent optional providers."""
import logging
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from examples import runtime


@pytest.mark.parametrize("telemetry,manager", [(False, False), (True, False), (False, True), (True, True)])
def test_project_providers(monkeypatch, caplog, telemetry, manager):
    caplog.set_level(logging.INFO)
    providers = []
    for enabled, capability, method in (
        (telemetry, runtime.AbstractObservabilityService, "get_telemetry_env_binding"),
        (manager, runtime.AbstractSecretManagerService, "get_secret_manager_env_binding"),
    ):
        if enabled:
            for name in ("first", "second"):
                provider = Mock(spec=capability)
                provider.name, provider.service_uuid, provider.state = name, name, "running"
                getattr(provider, method).return_value = {}
                providers.append(provider)
    bundle = SimpleNamespace(services=providers, server=SimpleNamespace(uuid="server", ip="127.0.0.1"))
    infra = SimpleNamespace(bundles=[bundle], get_bundle_by_service=lambda s: bundle)
    monkeypatch.setattr(runtime, "load_project_workspace", lambda: SimpleNamespace(infrastructure=infra))
    client, secret_client = Mock(), Mock()
    factory = Mock(return_value=client)
    loader = Mock(return_value=secret_client)
    setter = Mock()
    monkeypatch.setattr(runtime.OTelClient, "from_env", factory)
    monkeypatch.setattr(runtime, "load_secret_manager_from_env", loader)
    monkeypatch.setattr(runtime, "set_telemetry_client", setter)
    monkeypatch.setenv(runtime.SECRET_MANAGER_KEYFILE_ENV, "inherited-secret")
    monkeypatch.setenv(runtime.SECRET_MANAGER_KEYFILE_PW_ENV, "inherited-password")
    assert runtime.setup_runtime() == (client if telemetry else None, secret_client if manager else None)
    assert factory.call_count == int(telemetry)
    assert loader.call_count == int(manager)
    setter.assert_called_once_with(client if telemetry else None)
    for p in providers:
        method = ("get_telemetry_env_binding" if isinstance(p, runtime.AbstractObservabilityService)
                  else "get_secret_manager_env_binding")
        assert getattr(p, method).call_count == (1 if p.name == "first" else 0)
    if telemetry or manager:
        assert "selected first (first), server=server (127.0.0.1)" in caplog.text
    assert "inherited-secret" not in caplog.text
    assert f"telemetry={telemetry}, secret_manager={manager}" in caplog.text


@pytest.mark.parametrize("available", [False, True])
def test_tracker_required_and_first_selected(monkeypatch, available):
    trackers = [Mock(name="tracker1"), Mock(name="tracker2")] if available else []
    for tracker in trackers:
        tracker.state, tracker.service_uuid = "running", "uuid"
        tracker.get_secrets.return_value = {"service_url": "https://tracker.example"}
    infra = SimpleNamespace(bundles=[], filter_by_group=lambda group: trackers,
                            get_bundle_by_service=lambda s: None)
    monkeypatch.setattr(runtime, "load_project_workspace", lambda: SimpleNamespace(infrastructure=infra))
    monkeypatch.setattr(runtime, "set_telemetry_client", Mock())
    monkeypatch.setenv("MLFLOW_URI", "sqlite:///ignored.db")
    if not available:
        with pytest.raises(RuntimeError, match="requires a running MLflow"):
            runtime.setup_runtime(tracking=True)
    else:
        runtime.setup_runtime(tracking=True)
        assert runtime.os.environ["MLFLOW_URI"] == "https://tracker.example"
        trackers[0].get_secrets.assert_called_once()
        trackers[1].get_secrets.assert_not_called()


def test_project_environment_required(monkeypatch):
    monkeypatch.delenv("MLOX_PROJECT_PATH", raising=False)
    monkeypatch.delenv("MLOX_PROJECT_PASSWORD", raising=False)
    with pytest.raises(SystemExit):
        runtime.setup_runtime()
