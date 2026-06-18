from __future__ import annotations

from dataclasses import dataclass
from typing import Dict

import pytest

from mlox.service import AbstractService
from mlox.services.kubeflow.k8s import KubeflowService
from mlox.services.mlflow_mlserver.k3s import MLFlowMLServerK3sService


@dataclass
class DummyTemplateService(AbstractService):
    def setup(self, conn) -> None:
        pass

    def teardown(self, conn) -> None:
        pass

    def check(self, conn) -> Dict:
        return {"status": "running"}

    def get_secrets(self) -> Dict[str, Dict]:
        return {}

    def spin_up(self, conn) -> bool:
        return True

    def spin_down(self, conn) -> bool:
        return True


def _dummy_service() -> DummyTemplateService:
    return DummyTemplateService(
        name="dummy",
        service_config_id="dummy",
        template="unused",
        target_path="/tmp/dummy",
    )


def test_render_template_resolves_next_to_service_module() -> None:
    service = _dummy_service()

    rendered = service.render_template(
        "service-render-fixture.tmpl",
        {
            "name": "mlox",
            "quoted": service.yaml_scalar("value:with:colon"),
            "block": service.indent_block("line one\nline two", 2),
        },
    )

    assert "name: mlox" in rendered
    assert 'quoted: "value:with:colon"' in rendered
    assert "  line one" in rendered
    assert "  line two" in rendered
    assert "${HOME} $$ not touched" in rendered


def test_render_template_reports_missing_template() -> None:
    service = _dummy_service()

    with pytest.raises(FileNotFoundError, match="does-not-exist.tmpl"):
        service.render_template("does-not-exist.tmpl", {})


def test_render_template_reports_missing_variable() -> None:
    service = _dummy_service()

    with pytest.raises(KeyError, match="name"):
        service.render_template("service-render-fixture.tmpl", {})


def test_kubeflow_traefik_values_template_renders_valid_yaml() -> None:
    service = KubeflowService(
        name="Kubeflow",
        service_config_id="kubeflow",
        template="unused",
        target_path="/tmp/kubeflow",
    )

    rendered = service.render_template(
        "kubeflow-traefik-values.yaml.tmpl",
        {
            "ingress_service": service.ingress_service,
            "ingress_namespace": service.ingress_namespace,
            "ingress_port": service.ingress_port,
        },
    )
    assert f"port: {service.ingress_port}" in rendered
    assert f"exposedPort: {service.ingress_port}" in rendered
    assert "type: LoadBalancer" in rendered
    assert (
        "http://istio-ingressgateway.istio-system.svc.cluster.local:80" in rendered
    )


def test_mlflow_mlserver_k3s_manifest_template_renders_valid_documents() -> None:
    service = MLFlowMLServerK3sService(
        name="MLFlow-MLServer",
        service_config_id="mlflow-mlserver-3.8.1-k3s",
        template="unused",
        target_path="/tmp/mlflow-mlserver",
        dockerfile="unused",
        port=30432,
        model="demo-model/1",
        tracking_uri="https://mlflow.example.test",
        tracking_user="user",
        tracking_pw="pw",
    )

    rendered = service._render_manifest()
    assert "kind: Namespace" in rendered
    assert "kind: Deployment" in rendered
    assert "kind: Service" in rendered
    assert f"name: {service.namespace}" in rendered
    assert f"name: {service.deployment_name}" in rendered
    assert f"nodePort: {service.port}" in rendered
    assert "${" not in rendered
    assert "@" not in rendered
