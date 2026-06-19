from __future__ import annotations

from dataclasses import dataclass
from typing import Dict

import pytest

from mlox.service import AbstractService
from mlox.services.k8s_headlamp.k8s import K8sHeadlampService
from mlox.services.kubeapps.k8s import KubeAppsService
from mlox.services.kubeflow.k8s import KubeflowService
from mlox.services.mlflow_gateway.k3s import MLFlowGatewayK3sService
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


def test_kubeapps_templates_render_expected_resources() -> None:
    service = KubeAppsService(
        name="KubeApps",
        service_config_id="kubeapps",
        template="unused",
        target_path="/tmp/kubeapps",
    )

    ingress = service.render_template(
        "ingress.yaml.tmpl",
        {
            "ingress_name": "kubeapps-ingress",
            "namespace": service.namespace,
            "entrypoint": "websecure",
            "host_line": "    - http:",
            "path": "/kubeapps",
            "release_name": service.release_name,
            "backend_service_port": 80,
            "tls_hosts": " []",
            "tls_secret_name": "kubeapps-ingress-tls",
        },
    )
    binding = service.render_template(
        "admin-binding.yaml.tmpl",
        {
            "service_account_name": service.service_account_name,
            "namespace": service.namespace,
            "binding_name": service._cluster_role_binding_name(),
        },
    )

    assert "kind: Ingress" in ingress
    assert "path: /kubeapps" in ingress
    assert "kind: ServiceAccount" in binding
    assert "kind: ClusterRoleBinding" in binding
    assert "@" not in ingress + binding


def test_headlamp_templates_render_expected_resources() -> None:
    service = K8sHeadlampService(
        name="Headlamp",
        service_config_id="headlamp",
        template="unused",
        target_path="/tmp/headlamp",
    )

    ingress = service.render_template(
        "ingress.yaml.tmpl",
        {
            "ingress_name": "headlamp-ingress",
            "namespace": service.namespace,
            "annotations_block": "    kubernetes.io/ingress.class: traefik",
            "path": "/headlamp",
            "service_name": service.service_name,
            "backend_port": 8080,
        },
    )
    middleware = service.render_template(
        "middleware.yaml.tmpl",
        {
            "middleware_name": "headlamp-strip-prefix",
            "namespace": service.namespace,
            "path": "/headlamp",
        },
    )
    values = service.render_template(
        "gadgets-values.yaml.tmpl", {"service_name": service.service_name}
    )
    binding = service.render_template(
        "cluster-admin-binding.yaml.tmpl",
        {
            "binding_name": "headlamp-cluster-admin",
            "service_name": service.service_name,
            "namespace": service.namespace,
        },
    )

    rendered = ingress + middleware + values + binding
    assert "kind: Ingress" in ingress
    assert "kind: Middleware" in middleware
    assert f'claimName: "{service.service_name}"' in values
    assert "kind: ClusterRoleBinding" in binding
    assert "@" not in rendered


def test_mlflow_gateway_k3s_templates_render_expected_resources(tmp_path) -> None:
    serve_script = tmp_path / "serve.py"
    serve_script.write_text("print('gateway')\n", encoding="utf-8")
    service = MLFlowGatewayK3sService(
        name="MLflow Gateway",
        service_config_id="mlflow-gateway-3.8.1-k3s",
        template="unused",
        target_path="/tmp/mlflow-gateway",
        dockerfile="unused",
        serve_script=str(serve_script),
        start_script="unused",
        port=30433,
        tracking_uri="https://mlflow.example.test",
        tracking_user="user",
        tracking_pw="pw",
        requirements_txt="pydantic==2.0.0",
    )

    manifest = service._render_gateway_manifest()
    values = service._render_traefik_values()

    assert "kind: ConfigMap" in manifest
    assert "kind: Secret" in manifest
    assert "kind: Deployment" in manifest
    assert "print('gateway')" in manifest
    assert "pydantic==2.0.0" in manifest
    assert f"namespace: {service.namespace}" in manifest
    assert f"exposedPort: {service.port}" in values
    assert "gateway-auth" in values
    assert "@" not in manifest + values
