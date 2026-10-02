import numpy as np
import pytest
from types import SimpleNamespace

from examples.operations_demo.model import OperationsDemoModel, demonstration_batch
from examples.operations_demo import traffic


def test_demo_model_fault_is_isolated_to_pca_and_degrades_rmse(monkeypatch):
    monkeypatch.setattr("examples.operations_demo.model.mlflow.log_param", lambda *_: None)
    model = OperationsDemoModel()
    model.tracked_training()
    batch = demonstration_batch()

    healthy = model.live_predict(batch, {"corrupt": False})["prediction"]
    corrupt = model.live_predict(batch, {"corrupt": True})["prediction"]
    target = batch["target"]
    healthy_rmse = float(np.sqrt(np.mean((healthy - target) ** 2)))
    corrupt_rmse = float(np.sqrt(np.mean((corrupt - target) ** 2)))

    assert healthy_rmse < 1e-10
    assert corrupt_rmse > 1.0
    assert list(healthy.index) == list(batch.index)


def test_demonstration_batch_is_reproducible_and_labelled():
    first = demonstration_batch(8)
    second = demonstration_batch(8)

    assert first.equals(second)
    assert list(first.columns) == ["feature_1", "feature_2", "feature_3", "target"]


def test_demonstration_batch_supports_reproducible_sample_noise():
    first = demonstration_batch(
        32,
        rng=np.random.default_rng(7),
        feature_noise=0.03,
        label_noise=0.02,
    )
    second = demonstration_batch(
        32,
        rng=np.random.default_rng(7),
        feature_noise=0.03,
        label_noise=0.02,
    )
    noiseless_target = (
        first[["feature_1", "feature_2", "feature_3"]].to_numpy()
        @ np.array([1.25, -2.0, 0.75])
        + 0.15
    )

    assert first.equals(second)
    assert not np.allclose(first["target"], noiseless_target)


def _traffic_service(name, uuid, *, state="running", service_url=""):
    return SimpleNamespace(
        name=name,
        uuid=uuid,
        state=state,
        service_url=service_url,
        service_urls={},
    )


def test_traffic_loop_reports_and_switches_gateway_dependencies(monkeypatch):
    registry = _traffic_service(
        "MLflow", "registry-uuid", service_url="https://registry.example"
    )
    telemetry = _traffic_service(
        "OpenTelemetry", "telemetry-uuid", service_url="https://otel.example"
    )
    services = {service.uuid: service for service in (registry, telemetry)}

    class _Gateway(SimpleNamespace):
        def get_dependent_service(self, service_uuid):
            return services.get(service_uuid)

    first = _Gateway(
        name="Gateway A",
        uuid="gateway-aaaa",
        state="running",
        service_url="https://gateway-a.example",
        service_urls={},
        registry_uuid="registry-uuid",
        telemetry_uuid="telemetry-uuid",
        secret_manager_uuid=None,
        tls_secret_manager_uuid=None,
    )
    second = _Gateway(
        name="Gateway B",
        uuid="gateway-bbbb",
        state="running",
        service_url="https://gateway-b.example",
        service_urls={},
        registry_uuid="registry-uuid",
        telemetry_uuid=None,
        secret_manager_uuid=None,
        tls_secret_manager_uuid=None,
    )
    stopped = _Gateway(
        name="Gateway stopped",
        uuid="gateway-cccc",
        state="stopped",
        service_url="https://gateway-c.example",
        service_urls={},
    )
    workspace = SimpleNamespace(
        infrastructure=SimpleNamespace(
            bundles=[SimpleNamespace(services=[first, second, stopped])]
        )
    )
    monkeypatch.setattr(traffic, "MLFlowGatewayService", _Gateway)
    monkeypatch.setattr(traffic, "load_project_workspace", lambda: workspace)

    loop = traffic.TrafficLoop(2.0)
    status = "\n".join(loop.status_lines())

    assert "Gateway A (gateway-aaaa)" in status
    assert "endpoint=https://gateway-a.example" in status
    assert "MLflow (registry-uuid)" in status
    assert "OpenTelemetry (telemetry-uuid)" in status
    assert "Secret manager: not bound" in status
    assert "* Gateway A" in "\n".join(loop.gateway_lines())

    loop.select_gateway("gateway-b")
    assert loop.gateway is second
    assert "* Gateway B" in "\n".join(loop.gateway_lines())

    with pytest.raises(ValueError, match="not running"):
        loop.select_gateway("gateway-cccc")


def test_traffic_loop_rejects_unknown_or_ambiguous_gateway(monkeypatch):
    class _Gateway(SimpleNamespace):
        pass

    gateways = [
        _Gateway(name="A", uuid="shared-a", state="running", service_url="https://a"),
        _Gateway(name="B", uuid="shared-b", state="running", service_url="https://b"),
    ]
    workspace = SimpleNamespace(
        infrastructure=SimpleNamespace(
            bundles=[SimpleNamespace(services=gateways)]
        )
    )
    monkeypatch.setattr(traffic, "MLFlowGatewayService", _Gateway)
    monkeypatch.setattr(traffic, "load_project_workspace", lambda: workspace)

    loop = traffic.TrafficLoop(2.0)
    with pytest.raises(ValueError, match="ambiguous"):
        loop.select_gateway("shared")
    with pytest.raises(ValueError, match="No MLflow Gateway"):
        loop.select_gateway("missing")
