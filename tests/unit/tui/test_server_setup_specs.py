"""TUI server setup provider tests."""

from __future__ import annotations

from types import SimpleNamespace

from mlox.tui.servers.connector import setup_connector
from mlox.tui.servers.local import setup_local
from mlox.tui.servers.multipass import setup_multipass
from mlox.tui.servers.multipass_k3s import setup_multipass_k3s
from mlox.tui.servers.ubuntu import setup_native
from mlox.tui.servers.ubuntu_k3s import setup_k3s
from mlox.tui.servers.ubuntu_simple import setup_simple


def _config(name: str = "Ubuntu"):
    return SimpleNamespace(name=name)


def test_native_setup_maps_ssh_params() -> None:
    spec = setup_native(SimpleNamespace(), _config())

    params = spec.params(
        {"host": "1.2.3.4", "port": "2222", "user": "root", "password": "pw"},
        SimpleNamespace(),
    )

    assert params == {
        "${MLOX_IP}": "1.2.3.4",
        "${MLOX_PORT}": "2222",
        "${MLOX_ROOT}": "root",
        "${MLOX_ROOT_PW}": "pw",
    }


def test_simple_setup_maps_private_key_params() -> None:
    spec = setup_simple(SimpleNamespace(), _config())

    params = spec.params(
        {
            "host": "1.2.3.4",
            "port": "22",
            "user": "ubuntu",
            "password": "",
            "private_key": "key",
            "passphrase": "phrase",
        },
        SimpleNamespace(),
    )

    assert params["${MLOX_ROOT_PRIVATE_KEY}"] == "key"
    assert params["${MLOX_ROOT_PASSPHRASE}"] == "phrase"


def test_k3s_setup_maps_existing_controller_params() -> None:
    controller_server = SimpleNamespace(
        ip="10.0.0.1",
        uuid="controller-1",
        get_backend_status=lambda: {"k3s.token": "token"},
    )
    infra = SimpleNamespace(
        bundles=[SimpleNamespace(name="controller", server=controller_server)],
        list_kubernetes_controller=lambda: [
            SimpleNamespace(name="controller", server=controller_server)
        ],
    )
    spec = setup_k3s(infra, _config())

    params = spec.params(
        {
            "host": "10.0.0.2",
            "port": "22",
            "user": "root",
            "password": "pw",
            "k3s_controller_uuid": "controller-1",
        },
        infra,
    )

    assert params["${K3S_CONTROLLER_URL}"] == "https://10.0.0.1:6443"
    assert params["${K3S_CONTROLLER_TOKEN}"] == "token"
    assert params["${K3S_CONTROLLER_UUID}"] == "controller-1"


def test_multipass_setup_maps_vm_params() -> None:
    spec = setup_multipass(SimpleNamespace(), _config("Multipass"))

    params = spec.params(
        {
            "vm_name": "mlox-dev",
            "cpus": "4",
            "memory": "8G",
            "disk": "40G",
            "image": "24.04",
            "cloud_init": "",
            "launch_timeout": "600",
        },
        SimpleNamespace(),
    )

    assert params["${MULTIPASS_VM_NAME}"] == "mlox-dev"
    assert params["${MULTIPASS_CPUS}"] == "4"


def test_multipass_k3s_setup_includes_controller_params() -> None:
    spec = setup_multipass_k3s(SimpleNamespace(bundles=[]), _config("Multipass k3s"))

    params = spec.params(
        {
            "vm_name": "mlox-k3s",
            "cpus": "2",
            "memory": "4G",
            "disk": "20G",
            "image": "24.04",
            "cloud_init": "",
            "launch_timeout": "600",
            "k3s_controller_uuid": "",
        },
        SimpleNamespace(bundles=[]),
    )

    assert params["${K3S_CONTROLLER_URL}"] == ""
    assert params["${K3S_CONTROLLER_TOKEN}"] == ""


def test_connector_and_local_setup_map_params() -> None:
    connector = setup_connector(SimpleNamespace(bundles=[]), _config("Connector"))
    local = setup_local(SimpleNamespace(), _config("Localhost"))

    assert connector.params({"name": "external"}, SimpleNamespace()) == {
        "${MLOX_IP}": "external"
    }
    assert local.params({"user": "me", "password": ""}, SimpleNamespace()) == {
        "${MLOX_USER}": "me",
        "${MLOX_USER_PW}": "",
    }
