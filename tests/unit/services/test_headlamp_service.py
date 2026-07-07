from __future__ import annotations

from types import SimpleNamespace

from mlox.services.k8s_headlamp.k8s import K8sHeadlampService


BASE = {
    "name": "headlamp",
    "service_config_id": "headlamp-newest-k3s",
    "template": "/tmp/headlamp.yaml",
    "target_path": "/tmp/headlamp",
}


class FakeKubeExec:
    def __init__(self) -> None:
        self.calls = []
        self.files = {}
        self.service_port_output = "80"

    def _record(self, name, *args, **kwargs) -> None:
        self.calls.append((name, args, kwargs))

    def fs_create_dir(self, conn, path):
        self._record("fs_create_dir", path)

    def fs_write_file(self, conn, path, content):
        self._record("fs_write_file", path, content)
        self.files[path] = content

    def helm_repo_add(self, conn, *args, **kwargs):
        self._record("helm_repo_add", *args, **kwargs)

    def helm_upgrade_install(self, conn, **kwargs):
        self._record("helm_upgrade_install", **kwargs)
        return "installed"

    def k8s_apply_manifest(self, conn, manifest, **kwargs):
        self._record("k8s_apply_manifest", manifest, **kwargs)
        return "configured"

    def execute(self, conn, command, **kwargs):
        self._record("execute", command, **kwargs)
        return self.service_port_output


def _service(exec_: FakeKubeExec) -> K8sHeadlampService:
    service = K8sHeadlampService(**BASE)
    service.exec = exec_
    return service


def test_headlamp_setup_uses_chart_base_url_and_prefix_ingress() -> None:
    conn = SimpleNamespace(host="example.test")
    fake = FakeKubeExec()
    service = _service(fake)

    service.setup(conn)

    helm_call = next(call for call in fake.calls if call[0] == "helm_upgrade_install")
    assert helm_call[2] == {
        "release": "my-headlamp",
        "chart": "headlamp/headlamp",
        "namespace": "kube-system",
        "kubeconfig": "/etc/rancher/k3s/k3s.yaml",
        "create_namespace": True,
        "values": {"config.baseURL": "/headlamp"},
    }

    ingress = fake.files["/tmp/headlamp/my-headlamp-ingress.yaml"]
    assert "path: /headlamp" in ingress
    assert "pathType: Prefix" in ingress
    assert "router.middlewares" not in ingress
    assert "kind: Middleware" not in ingress

    apply_call = next(
        call
        for call in fake.calls
        if call[0] == "k8s_apply_manifest"
        and call[1][0] == "/tmp/headlamp/my-headlamp-ingress.yaml"
    )
    assert apply_call[2] == {
        "namespace": "kube-system",
        "kubeconfig": "/etc/rancher/k3s/k3s.yaml",
    }
    assert service.service_urls["Headlamp"] == "https://example.test:443/headlamp/"
    assert service.service_ports["Headlamp"] == 443
    assert service.state == "running"


def test_headlamp_root_path_keeps_empty_chart_base_url() -> None:
    fake = FakeKubeExec()
    service = _service(fake)
    service.ingress_path = "/"

    assert service._helm_values() == {"config.baseURL": ""}
