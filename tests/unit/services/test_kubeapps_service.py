from __future__ import annotations

import json
import shlex
from contextlib import contextmanager
from types import SimpleNamespace

from mlox.services.kubeapps.k8s import KubeAppsService


BASE = {
    "name": "kubeapps",
    "service_config_id": "kubeapps-newest-k3s",
    "template": "/tmp/kubeapps.yaml",
    "target_path": "/tmp/kubeapps",
}


class FakeKubeExec:
    def __init__(self):
        self.calls = []
        self.files = {}
        self.namespaces = set()
        self.namespace_phases = {}
        self.node_port_output = "31161"
        self.helm_status_output = json.dumps({"info": {"status": "deployed"}})
        self.token_output = "login-token"
        self.history = []

    def _record(self, name, *args, **kwargs):
        self.calls.append((name, args, kwargs))

    def fs_create_dir(self, conn, path):
        self._record("fs_create_dir", path)

    def fs_delete_dir(self, conn, path):
        self._record("fs_delete_dir", path)

    def fs_write_file(self, conn, path, content):
        self._record("fs_write_file", path)
        self.files[path] = content

    def k8s_namespace_exists(self, conn, namespace, **kwargs):
        self._record("k8s_namespace_exists", namespace, **kwargs)
        return namespace in self.namespaces

    def helm_repo_add(self, conn, *args, **kwargs):
        self._record("helm_repo_add", *args, **kwargs)

    def helm_repo_update(self, conn, *args, **kwargs):
        self._record("helm_repo_update", *args, **kwargs)

    def helm_upgrade_install(self, conn, **kwargs):
        self._record("helm_upgrade_install", **kwargs)
        return "installed"

    def helm_status(self, conn, **kwargs):
        self._record("helm_status", **kwargs)
        return self.helm_status_output

    def helm_uninstall(self, conn, **kwargs):
        self._record("helm_uninstall", **kwargs)

    def k8s_delete_resource(self, conn, *args, **kwargs):
        self._record("k8s_delete_resource", *args, **kwargs)

    def k8s_apply_manifest(self, conn, manifest, **kwargs):
        self._record("k8s_apply_manifest", manifest, **kwargs)

    def k8s_create_token(self, conn, **kwargs):
        self._record("k8s_create_token", **kwargs)
        return self.token_output

    def execute(self, conn, command, **kwargs):
        self._record("execute", command, **kwargs)
        namespace = self._namespace_from_get_command(command)
        if namespace:
            return self.namespace_phases.get(namespace, "")
        return self.node_port_output

    def _namespace_from_get_command(self, command):
        parts = shlex.split(command)
        try:
            get_index = parts.index("get")
        except ValueError:
            return None
        if len(parts) > get_index + 2 and parts[get_index + 1] == "namespace":
            return parts[get_index + 2]
        return None


def _service(exec_: FakeKubeExec) -> KubeAppsService:
    service = KubeAppsService(**BASE)
    service.exec = exec_
    return service


class FakeServer:
    @contextmanager
    def get_server_connection(self):
        yield SimpleNamespace(host="example.test")


def test_kubeapps_setup_installs_sap_oci_chart_as_nodeport():
    conn = SimpleNamespace(host="example.test")
    fake = FakeKubeExec()
    service = _service(fake)

    service.setup(conn)

    call_names = [name for name, _, _ in fake.calls]
    assert "helm_repo_add" not in call_names
    assert "helm_repo_update" not in call_names

    helm_call = next(call for call in fake.calls if call[0] == "helm_upgrade_install")
    assert helm_call[2] == {
        "release": "kubeapps-0",
        "chart": "oci://ghcr.io/sap/kubeapps/kubeapps",
        "namespace": "kubeapps-0",
        "kubeconfig": "/etc/rancher/k3s/k3s.yaml",
        "create_namespace": True,
        "values": {
            "frontend.service.type": "NodePort",
            "frontend.service.nodePorts.http": "30080",
            "dashboard.image.tag": "v3.0.0",
            "apprepository.image.tag": "v3.0.0",
            "apprepository.syncImage.tag": "v3.0.0",
            "kubeappsapis.image.tag": "v3.0.0",
            "pinnipedProxy.image.tag": "v3.0.0",
            "ociCatalog.image.tag": "v3.0.0",
            "postgresql.fullnameOverride": "kubeapps-0-postgresql",
        },
    }
    assert service.service_urls["KubeApps"] == "http://example.test:31161"
    assert service.service_ports["KubeApps"] == 31161
    assert service.node_port == 31161
    assert service.state == "running"

    assert service.namespace == "kubeapps-0"
    assert service.release_name == "kubeapps-0"
    manifest = fake.files["/tmp/kubeapps/kubeapps-0-kubeapps-admin-cluster-admin.yaml"]
    assert "name: kubeapps-admin" in manifest
    assert "name: cluster-admin" in manifest


def test_kubeapps_setup_ignores_unsuffixed_namespace_and_starts_at_zero():
    conn = SimpleNamespace(host="example.test")
    fake = FakeKubeExec()
    fake.namespace_phases["kubeapps"] = "Active"
    service = _service(fake)

    service.setup(conn)

    helm_call = next(call for call in fake.calls if call[0] == "helm_upgrade_install")
    assert service.namespace == "kubeapps-0"
    assert service.release_name == "kubeapps-0"
    assert helm_call[2]["namespace"] == "kubeapps-0"
    assert helm_call[2]["release"] == "kubeapps-0"
    assert helm_call[2]["values"]["postgresql.fullnameOverride"] == "kubeapps-0-postgresql"
    assert "/tmp/kubeapps/kubeapps-0-kubeapps-admin-cluster-admin.yaml" in fake.files


def test_kubeapps_setup_increments_suffix_until_namespace_is_available():
    conn = SimpleNamespace(host="example.test")
    fake = FakeKubeExec()
    fake.namespace_phases["kubeapps-0"] = "Active"
    service = _service(fake)

    service.setup(conn)

    helm_call = next(call for call in fake.calls if call[0] == "helm_upgrade_install")
    assert service.namespace == "kubeapps-1"
    assert service.release_name == "kubeapps-1"
    assert helm_call[2]["namespace"] == "kubeapps-1"
    assert helm_call[2]["values"]["postgresql.fullnameOverride"] == "kubeapps-1-postgresql"


def test_kubeapps_get_login_token_uses_admin_service_account():
    fake = FakeKubeExec()
    service = _service(fake)
    bundle = SimpleNamespace(server=FakeServer())

    assert service.get_login_token(bundle) == "login-token"

    token_call = next(call for call in fake.calls if call[0] == "k8s_create_token")
    assert token_call[2] == {
        "service_account": "kubeapps-admin",
        "namespace": "kubeapps",
        "kubeconfig": "/etc/rancher/k3s/k3s.yaml",
    }


def test_kubeapps_check_maps_deployed_helm_release_to_running():
    fake = FakeKubeExec()
    service = _service(fake)

    assert service.check(SimpleNamespace(host="example.test")) == {
        "status": "running",
        "details": "Helm release is deployed.",
    }


def test_kubeapps_check_reports_failed_helm_release_as_error():
    fake = FakeKubeExec()
    fake.helm_status_output = json.dumps({"info": {"status": "failed"}})
    service = _service(fake)

    assert service.check(SimpleNamespace(host="example.test")) == {
        "status": "error",
        "details": "Helm release status: failed.",
    }
