import json
import logging

import pytest

from mlox.config import get_stacks_path, load_config
from mlox.infra import Bundle, Infrastructure
from tests.integration.conftest import wait_for_service_ready
from tests.integration.helpers import add_service, remove_service


pytestmark = [pytest.mark.integration, pytest.mark.kubernetes]
logger = logging.getLogger(__name__)


def _add_kubernetes_service(ubuntu_k3s_server, service_dir: str, config_name: str):
    infra = Infrastructure()
    bundle = Bundle(name=ubuntu_k3s_server.ip, server=ubuntu_k3s_server)
    infra.bundles.append(bundle)

    config = load_config(get_stacks_path(), service_dir, config_name)
    bundle_added = add_service(infra, ubuntu_k3s_server.ip, config, params={})
    if not bundle_added:
        pytest.skip(f"Failed to add Kubernetes service from config {config_name}")
    service = bundle_added.services[-1]
    return infra, bundle_added, service


def _remove_service(infra: Infrastructure, service_name: str) -> None:
    result = remove_service(infra, service_name)
    if not result.success:
        logger.warning("Failed to remove Kubernetes service %s: %s", service_name, result.message)


def _headlamp_status(service, bundle) -> dict[str, str]:
    with bundle.server.get_server_connection() as conn:
        status = service.exec.helm_status(
            conn,
            release=service.service_name,
            namespace=service.namespace,
            kubeconfig=service.kubeconfig,
            output_format="json",
        )
    if not status:
        return {"status": "unknown", "details": "helm status returned no output"}
    try:
        payload = json.loads(status)
    except json.JSONDecodeError:
        return {"status": "unknown", "details": status}
    release_state = payload.get("info", {}).get("status", "unknown").lower()
    return {
        "status": "running" if release_state == "deployed" else "unknown",
        "helm_status": release_state,
    }


def test_headlamp_service_installs_on_k3s(ubuntu_k3s_server):
    infra, bundle, service = _add_kubernetes_service(
        ubuntu_k3s_server,
        "/k8s_headlamp",
        "mlox.headlamp.yaml",
    )
    try:
        with ubuntu_k3s_server.get_server_connection() as conn:
            service.setup(conn)

        status = wait_for_service_ready(
            service,
            bundle,
            check_fn=lambda: _headlamp_status(service, bundle),
            retries=18,
            interval=10,
        )
        assert status.get("status") == "running"
        assert service.service_urls.get("Headlamp", "").startswith("https://")
        assert service.service_ports.get("Headlamp")
    finally:
        _remove_service(infra, service.name)


def test_kubeapps_service_installs_on_k3s(ubuntu_k3s_server):
    infra, bundle, service = _add_kubernetes_service(
        ubuntu_k3s_server,
        "/kubeapps",
        "mlox.kubeapps.yaml",
    )
    try:
        with ubuntu_k3s_server.get_server_connection() as conn:
            service.setup(conn)

        status = wait_for_service_ready(service, bundle, retries=24, interval=10)
        assert status.get("status") == "running"
        assert service.service_urls.get("KubeApps", "").startswith("https://")
        assert service.service_ports.get("KubeApps")
    finally:
        _remove_service(infra, service.name)
