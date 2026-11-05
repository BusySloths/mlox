"""Contract and integration tests for server and service log capabilities."""

from contextlib import nullcontext
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from mlox.application.use_cases import servers, services
from mlox.config import load_all_server_configs, load_all_service_configs, _load_build_class
from mlox.logs import LogSource, supports_logs
from mlox.server import AbstractLogServer, ServerCapability
from mlox.servers.ubuntu.native import UbuntuNativeServer
from mlox.service import AbstractLogService, ServiceCapability
from mlox.services.mlflow_mlserver.k3s import MLFlowMLServerK3sService


def test_advertised_catalog_log_capabilities_have_a_concrete_contract():
    service_configs = load_all_service_configs(include_plugins=False)
    server_configs = load_all_server_configs(include_plugins=False)
    for config in service_configs + server_configs:
        advertised = config.service_capabilities() | config.server_capabilities()
        if "logs" in advertised:
            cls = _load_build_class(config)
            assert issubclass(cls, LogSource)
            assert issubclass(cls, AbstractLogService if config in service_configs else AbstractLogServer)
            assert not cls.__abstractmethods__


def test_ubuntu_journal_source_validates_and_uses_privileged_executor():
    server = UbuntuNativeServer(ip="example", root="root", root_pw="pw", service_config_id="cfg")
    conn = SimpleNamespace(sudo=Mock(return_value=SimpleNamespace(exited=0, stdout="journal line\n", stderr="")))
    assert supports_logs(server)
    assert server.log_labels() == ["System journal"]
    assert server.log_tail(conn, label="System journal", tail=5) == "journal line"
    args, kwargs = conn.sudo.call_args
    assert args[0] == "journalctl --no-pager --output=short-iso -n 5"
    assert kwargs["hide"] is True
    for invalid in (0, -1, "5; reboot"):
        with pytest.raises(ValueError):
            server.log_tail(object(), tail=invalid)
    with pytest.raises(ValueError):
        server.log_tail(object(), label="other")
    conn.sudo.return_value = SimpleNamespace(exited=1, stdout="", stderr="[sudo] password: denied")
    with pytest.raises(RuntimeError, match="Journal retrieval failed.*denied"):
        server.log_tail(conn)


def test_server_log_use_case_checks_capability_and_propagates_errors():
    server = SimpleNamespace(
        capabilities={ServerCapability.LOGS}, log_labels=lambda: ["journal"],
        log_tail=Mock(return_value="hello"), get_server_connection=lambda: nullcontext("conn"),
    )
    infra = SimpleNamespace(get_bundle_by_ip=lambda ip: SimpleNamespace(server=server))
    project = SimpleNamespace(infrastructure=infra)
    assert servers.server_logs(project, ip="host", tail=3).data == {"logs": "hello"}
    server.log_tail.assert_called_once_with("conn", label="journal", tail=3)
    assert not servers.server_logs(project, ip="host", label="invalid").success
    assert not servers.server_logs(project, ip="host", tail=0).success
    server.log_tail.side_effect = RuntimeError("journal unavailable")
    assert "journal unavailable" in servers.server_logs(project, ip="host").message
    server.capabilities = set()
    assert not servers.server_logs(project, ip="host").success


def test_unadvertised_service_logs_are_rejected():
    service = SimpleNamespace(capabilities=set(), log_labels=lambda: ["x"], log_tail=Mock())
    infra = SimpleNamespace(get_service=lambda name: service)
    result = services.service_logs(SimpleNamespace(infrastructure=infra), name="x")
    assert not result.success
    assert "does not support logs" in result.message
    service.log_tail.assert_not_called()


def test_kubernetes_mlserver_uses_kubernetes_logs():
    service = MLFlowMLServerK3sService(
        name="mlserver", service_config_id="cfg", template="unused", target_path="/tmp/x",
        dockerfile="unused", port=30432, model="model", tracking_uri="uri",
        tracking_user="user", tracking_pw="pw",
    )
    service.exec.k8s_resource_log_tail = Mock(return_value="pod logs")
    assert ServiceCapability.LOGS in service.capabilities
    assert service.log_tail("conn", tail=7) == "pod logs"
    service.exec.k8s_resource_log_tail.assert_called_once_with(
        "conn", f"deployment/{service.deployment_name}", namespace=service.namespace,
        tail=7, kubeconfig=service.kubeconfig, container="mlserver",
    )
