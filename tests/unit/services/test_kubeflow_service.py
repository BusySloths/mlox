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
        return self.apply_results.pop(0)

    def k8s_apply_manifest(self, conn, manifest, **kwargs):
        self._record("k8s_apply_manifest", manifest, **kwargs)
        return "ingress configured"

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
        "kubectl --kubeconfig /etc/rancher/k3s/k3s.yaml apply -k "
        "'https://github.com/kubeflow/manifests/example?ref=v1.10.1'",
    )
    assert execute_call[2] == {
        "group": TaskGroup.KUBERNETES,
        "sudo": True,
        "description": "Apply Kubeflow manifests",
    }

    ingress_path = "/tmp/kubeflow/kubeflow-ingress.yaml"
    ingress = executor.files[ingress_path]
    assert "ingressClassName: traefik" in ingress
    assert "traefik.ingress.kubernetes.io/router.entrypoints: web" in ingress
    assert "namespace: istio-system" in ingress
    assert "name: istio-ingressgateway" in ingress
    assert "number: 80" in ingress
    assert service.service_urls == {"Kubeflow": "http://cluster.example:80/"}
    assert service.service_ports == {"Kubeflow": 80}
    assert service.state == "running"


def test_setup_retries_manifest_apply_for_crd_discovery():
    executor = FakeKubernetesExec()
    executor.apply_results = [None, None, "configured"]
    service = _service(executor)

    service.setup(SimpleNamespace(host="cluster.example"))

    apply_calls = [
        call
        for call in executor.calls
        if call[0] == "execute" and " apply -k " in call[1][0]
    ]
    assert len(apply_calls) == 3
    assert service.state == "running"


def test_setup_stops_when_upstream_manifests_fail():
    executor = FakeKubernetesExec()
    executor.apply_results = [None, None, None]
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


def test_teardown_removes_ingress_and_upstream_manifests():
    executor = FakeKubernetesExec()
    service = _service(executor)
    service.service_urls["Kubeflow"] = "http://cluster.example:80/"
    service.service_ports["Kubeflow"] = 80

    service.teardown(SimpleNamespace())

    delete_ingress = next(
        call for call in executor.calls if call[0] == "k8s_delete_resource"
    )
    assert delete_ingress[1] == ("ingress", "kubeflow")
    assert delete_ingress[2] == {
        "namespace": "istio-system",
        "kubeconfig": "/etc/rancher/k3s/k3s.yaml",
    }
    delete_manifests = next(
        call
        for call in executor.calls
        if call[0] == "execute" and " delete -k " in call[1][0]
    )
    assert delete_manifests[1] == (
        "kubectl --kubeconfig /etc/rancher/k3s/k3s.yaml delete -k "
        "'https://github.com/kubeflow/manifests/example?ref=v1.10.1' "
        "--ignore-not-found",
    )
    assert service.service_urls == {}
    assert service.service_ports == {}
    assert service.state == "un-initialized"
