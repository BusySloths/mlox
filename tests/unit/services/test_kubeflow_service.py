import json
from types import SimpleNamespace

from mlox.executors import TaskGroup
from mlox.services.kubeflow.k8s import KubeflowService


BASE = {
    "name": "kubeflow",
    "service_config_id": "kubeflow-1.10.1-k3s",
    "template": "/tmp/kubeflow.yaml",
    "target_path": "/tmp/kubeflow",
}


class FakeKubernetesExec:
    def __init__(self):
        self.calls = []
        self.files = {}
        self.apply_results = ["configured"]
        self.cookie_config_result = "deployment.apps/jupyter-web-app-deployment updated"
        self.minio_image_result = "deployment.apps/minio image updated"
        self.helm_repo_result = "repository added"
        self.helm_install_result = "release installed"
        self.webhook_result = "deployment successfully rolled out"
        self.auth_result = "deployment successfully rolled out"
        self.status = json.dumps(
            {
                "spec": {"replicas": 1},
                "status": {"availableReplicas": 1},
            }
        )

    def _record(self, name, *args, **kwargs):
        self.calls.append((name, args, kwargs))

    def fs_create_dir(self, conn, path):
        self._record("fs_create_dir", path)

    def fs_write_file(self, conn, path, content):
        self._record("fs_write_file", path, content)
        self.files[path] = content

    def fs_delete_dir(self, conn, path):
        self._record("fs_delete_dir", path)

    def execute(self, conn, command, **kwargs):
        self._record("execute", command, **kwargs)
        if " get deployment centraldashboard " in f" {command} ":
            return self.status
        if " rollout status deployment/webhook " in f" {command} ":
            return self.webhook_result
        if (
            " rollout status deployment/kserve-controller-manager "
            in f" {command} "
        ):
            return self.webhook_result
        if " set image deployment/minio " in f" {command} ":
            return self.minio_image_result
        if " rollout " in f" {command} ":
            return self.auth_result
        if " set env deployment/oauth2-proxy " in f" {command} ":
            return self.auth_result
        if " set env deployment/jupyter-web-app-deployment " in f" {command} ":
            return self.cookie_config_result
        return self.apply_results.pop(0)

    def helm_repo_add(self, conn, *args, **kwargs):
        self._record("helm_repo_add", *args, **kwargs)
        return self.helm_repo_result

    def helm_upgrade_install(self, conn, *args, **kwargs):
        self._record("helm_upgrade_install", *args, **kwargs)
        return self.helm_install_result

    def helm_uninstall(self, conn, *args, **kwargs):
        self._record("helm_uninstall", *args, **kwargs)
        return "release uninstalled"

    def k8s_apply_manifest(self, conn, manifest, **kwargs):
        self._record("k8s_apply_manifest", manifest, **kwargs)
        return "ingress configured"

    def k8s_patch_resource(self, conn, *args, **kwargs):
        self._record("k8s_patch_resource", *args, **kwargs)
        return "secret patched"

    def k8s_delete_resource(self, conn, *args, **kwargs):
        self._record("k8s_delete_resource", *args, **kwargs)


def _service(executor):
    service = KubeflowService(**BASE)
    service.exec = executor
    return service


def test_setup_applies_upstream_manifests_and_traefik_ingress():
    executor = FakeKubernetesExec()
    service = _service(executor)

    service.setup(SimpleNamespace(host="cluster.example"))

    execute_call = next(call for call in executor.calls if call[0] == "execute")
    assert execute_call[1] == (
        "kubectl --kubeconfig /etc/rancher/k3s/k3s.yaml apply "
        "--server-side --force-conflicts -k "
        "'https://github.com/kubeflow/manifests/example?ref=v1.10.1'",
    )
    assert execute_call[2] == {
        "group": TaskGroup.KUBERNETES,
        "sudo": True,
        "description": "Apply Kubeflow manifests",
    }
    minio_image_call = next(
        call
        for call in executor.calls
        if call[0] == "execute" and " set image deployment/minio " in call[1][0]
    )
    assert minio_image_call[1] == (
        "kubectl --kubeconfig /etc/rancher/k3s/k3s.yaml "
        "-n kubeflow set image deployment/minio "
        "minio=docker.io/minio/minio:RELEASE.2019-08-14T20-37-41Z",
    )
    assert minio_image_call[2] == {
        "group": TaskGroup.KUBERNETES,
        "sudo": True,
        "description": "Use the supported MinIO image for Kubeflow Pipelines",
    }
    pipeline_waits = [
        call
        for call in executor.calls
        if call[0] == "execute"
        and " -n kubeflow rollout status deployment/" in call[1][0]
        and "--timeout=300s" in call[1][0]
    ]
    assert [call[1][0] for call in pipeline_waits] == [
        "kubectl --kubeconfig /etc/rancher/k3s/k3s.yaml "
        "-n kubeflow rollout status deployment/mysql --timeout=300s",
        "kubectl --kubeconfig /etc/rancher/k3s/k3s.yaml "
        "-n kubeflow rollout status deployment/minio --timeout=300s",
        "kubectl --kubeconfig /etc/rancher/k3s/k3s.yaml "
        "-n kubeflow rollout status deployment/ml-pipeline --timeout=300s",
        "kubectl --kubeconfig /etc/rancher/k3s/k3s.yaml "
        "-n kubeflow rollout status deployment/ml-pipeline-ui --timeout=300s",
    ]
    cookie_config_call = next(
        call
        for call in executor.calls
        if call[0] == "execute"
        and " set env deployment/jupyter-web-app-deployment " in call[1][0]
    )
    assert cookie_config_call[1] == (
        "kubectl --kubeconfig /etc/rancher/k3s/k3s.yaml "
        "-n kubeflow set env deployment/jupyter-web-app-deployment "
        "APP_SECURE_COOKIES=true",
    )
    assert cookie_config_call[2] == {
        "group": TaskGroup.KUBERNETES,
        "sudo": True,
        "description": "Configure secure Jupyter cookies",
    }
    session_key_command = next(
        call[1][0]
        for call in executor.calls
        if call[0] == "execute"
        and " set env deployment/oauth2-proxy " in call[1][0]
    )
    session_key_prefix = (
        "kubectl --kubeconfig /etc/rancher/k3s/k3s.yaml "
        "-n oauth2-proxy set env deployment/oauth2-proxy "
        "OAUTH2_PROXY_COOKIE_SECRET="
    )
    assert session_key_command.startswith(session_key_prefix)
    assert len(session_key_command.removeprefix(session_key_prefix)) == 32
    restart_commands = [
        call[1][0]
        for call in executor.calls
        if call[0] == "execute" and " rollout restart " in call[1][0]
    ]
    assert restart_commands == [
        "kubectl --kubeconfig /etc/rancher/k3s/k3s.yaml "
        "-n istio-system rollout restart deployment/istiod",
    ]

    values_path = "/tmp/kubeflow/kubeflow-traefik-values.yaml"
    values = executor.files[values_path]
    helm_install = next(
        call for call in executor.calls if call[0] == "helm_upgrade_install"
    )
    assert helm_install[2] == {
        "release": "kubeflow-traefik",
        "chart": "kubeflow-traefik/traefik",
        "namespace": "kubeflow-traefik",
        "kubeconfig": "/etc/rancher/k3s/k3s.yaml",
        "create_namespace": True,
        "extra_args": [
            "--version",
            "34.4.1",
            "-f",
            values_path,
            "--wait",
            "--timeout",
            "5m",
        ],
    }
    assert "ingressClass:\n  enabled: false" in values
    assert "kubernetesCRD:\n    enabled: false" in values
    assert "kubernetesIngress:\n    enabled: false" in values
    assert "file:\n    enabled: true" in values
    assert "rule: PathPrefix(`/`)" in values
    assert (
        "url: http://istio-ingressgateway.istio-system.svc.cluster.local:80"
        in values
    )
    assert "port: 8443" in values
    assert "exposedPort: 8443" in values
    assert not any(call[0] == "k8s_apply_manifest" for call in executor.calls)
    legacy_deletes = [
        call for call in executor.calls if call[0] == "k8s_delete_resource"
    ]
    assert [call[1] for call in legacy_deletes] == [
        ("ingress", "kubeflow"),
        ("ingress", "kubeflow-entry"),
        ("ingress", "kubeflow-routes"),
        ("middleware", "kubeflow-auth-redirect"),
        ("middleware", "kubeflow-strip-prefix"),
    ]
    assert service.service_urls == {"Kubeflow": "https://cluster.example:8443/"}
    assert service.service_ports == {"Kubeflow": 8443}
    assert service.state == "running"


def test_setup_retries_manifest_apply_for_crd_discovery():
    executor = FakeKubernetesExec()
    executor.apply_results = [None, None, "configured"]
    service = _service(executor)

    service.setup(SimpleNamespace(host="cluster.example"))

    apply_calls = [
        call
        for call in executor.calls
        if call[0] == "execute" and " apply --server-side " in call[1][0]
    ]
    assert len(apply_calls) == 3
    knative_webhook_waits = [
        call
        for call in executor.calls
        if call[0] == "execute"
        and " rollout status deployment/webhook " in call[1][0]
    ]
    assert len(knative_webhook_waits) == 2
    assert knative_webhook_waits[0][1] == (
        "kubectl --kubeconfig /etc/rancher/k3s/k3s.yaml "
        "-n knative-serving rollout status deployment/webhook --timeout=120s",
    )
    assert knative_webhook_waits[0][2] == {
        "group": TaskGroup.KUBERNETES,
        "sudo": True,
        "description": "Wait for the Knative admission webhook",
    }
    kserve_webhook_waits = [
        call
        for call in executor.calls
        if call[0] == "execute"
        and " rollout status deployment/kserve-controller-manager "
        in call[1][0]
    ]
    assert len(kserve_webhook_waits) == 2
    assert kserve_webhook_waits[0][1] == (
        "kubectl --kubeconfig /etc/rancher/k3s/k3s.yaml "
        "-n kubeflow rollout status deployment/kserve-controller-manager "
        "--timeout=120s",
    )
    assert kserve_webhook_waits[0][2] == {
        "group": TaskGroup.KUBERNETES,
        "sudo": True,
        "description": "Wait for the KServe admission webhook",
    }
    assert service.state == "running"


def test_setup_stops_when_upstream_manifests_fail():
    executor = FakeKubernetesExec()
    executor.apply_results = [None, None, None]
    service = _service(executor)

    service.setup(SimpleNamespace(host="cluster.example"))

    webhook_waits = [
        call
        for call in executor.calls
        if call[0] == "execute"
        and (
            " rollout status deployment/webhook " in call[1][0]
            or " rollout status deployment/kserve-controller-manager "
            in call[1][0]
        )
    ]
    assert len(webhook_waits) == 4
    assert not any(call[0] == "helm_upgrade_install" for call in executor.calls)
    assert service.state == "unknown"


def test_setup_stops_when_jupyter_cookie_configuration_fails():
    executor = FakeKubernetesExec()
    executor.cookie_config_result = None
    service = _service(executor)

    service.setup(SimpleNamespace(host="cluster.example"))

    assert not any(call[0] == "helm_upgrade_install" for call in executor.calls)
    assert service.state == "unknown"


def test_setup_stops_when_minio_image_replacement_fails():
    executor = FakeKubernetesExec()
    executor.minio_image_result = None
    service = _service(executor)

    service.setup(SimpleNamespace(host="cluster.example"))

    assert not any(
        call[0] == "execute" and " rollout status deployment/mysql " in call[1][0]
        for call in executor.calls
    )
    assert not any(call[0] == "helm_upgrade_install" for call in executor.calls)
    assert service.state == "unknown"


def test_setup_stops_when_pipeline_api_does_not_become_ready():
    executor = FakeKubernetesExec()
    service = _service(executor)
    original_execute = executor.execute

    def execute(conn, command, **kwargs):
        if " rollout status deployment/ml-pipeline " in f" {command} ":
            executor._record("execute", command, **kwargs)
            return None
        return original_execute(conn, command, **kwargs)

    executor.execute = execute
    service.setup(SimpleNamespace(host="cluster.example"))

    assert not any(
        call[0] == "execute"
        and " rollout status deployment/ml-pipeline-ui " in call[1][0]
        for call in executor.calls
    )
    assert not any(call[0] == "helm_upgrade_install" for call in executor.calls)
    assert service.state == "unknown"


def test_setup_stops_when_dedicated_traefik_install_fails():
    executor = FakeKubernetesExec()
    executor.helm_install_result = None
    service = _service(executor)

    service.setup(SimpleNamespace(host="cluster.example"))

    assert not any(call[0] == "k8s_apply_manifest" for call in executor.calls)
    assert service.state == "unknown"


def test_check_reports_dashboard_availability():
    executor = FakeKubernetesExec()
    service = _service(executor)

    assert service.check(SimpleNamespace()) == {
        "status": "running",
        "details": "Kubeflow central dashboard is available.",
    }


def test_check_reports_dashboard_starting():
    executor = FakeKubernetesExec()
    executor.status = json.dumps(
        {
            "spec": {"replicas": 2},
            "status": {"availableReplicas": 1},
        }
    )
    service = _service(executor)

    assert service.check(SimpleNamespace()) == {
        "status": "starting",
        "details": "Kubeflow central dashboard has 1/2 available replicas.",
    }


def test_get_secrets_returns_initial_dex_credentials():
    executor = FakeKubernetesExec()
    service = _service(executor)
    service.service_urls["Kubeflow"] = "https://cluster.example:8443/"

    assert service.get_secrets() == {
        "kubeflow_dex_credentials": {
            "email": "user@example.com",
            "password": "12341234",
            "service_url": "https://cluster.example:8443/",
        }
    }


def test_teardown_removes_ingress_and_upstream_manifests():
    executor = FakeKubernetesExec()
    service = _service(executor)
    service.service_urls["Kubeflow"] = "https://cluster.example:8443/"
    service.service_ports["Kubeflow"] = 8443

    service.teardown(SimpleNamespace())

    delete_resources = [
        call for call in executor.calls if call[0] == "k8s_delete_resource"
    ]
    assert [call[1] for call in delete_resources] == [
        ("ingress", "kubeflow"),
        ("ingress", "kubeflow-entry"),
        ("ingress", "kubeflow-routes"),
        ("middleware", "kubeflow-auth-redirect"),
        ("middleware", "kubeflow-strip-prefix"),
    ]
    assert all(
        call[2]
        == {
            "namespace": "istio-system",
            "kubeconfig": "/etc/rancher/k3s/k3s.yaml",
            "extra_args": ["--wait=false", "--request-timeout=120s"],
        }
        for call in delete_resources
    )
    helm_uninstall = next(
        call for call in executor.calls if call[0] == "helm_uninstall"
    )
    assert helm_uninstall[2] == {
        "release": "kubeflow-traefik",
        "namespace": "kubeflow-traefik",
        "kubeconfig": "/etc/rancher/k3s/k3s.yaml",
        "extra_args": ["--timeout=120s"],
        "ignore_missing": True,
    }
    delete_manifests = next(
        call
        for call in executor.calls
        if call[0] == "execute" and " delete --wait=false " in call[1][0]
    )
    assert delete_manifests[1] == (
        "timeout --signal=TERM --kill-after=10s 120s "
        "kubectl --kubeconfig /etc/rancher/k3s/k3s.yaml delete "
        "--wait=false --request-timeout=120s -k "
        "'https://github.com/kubeflow/manifests/example?ref=v1.10.1' "
        "--ignore-not-found",
    )
    assert service.service_urls == {}
    assert service.service_ports == {}
    assert service.state == "un-initialized"
