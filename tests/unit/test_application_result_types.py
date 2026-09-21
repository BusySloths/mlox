from __future__ import annotations

from typing import get_type_hints

from mlox.application.payloads import (
    BundleData,
    ListConfigsData,
    ListModelsData,
    ListServersData,
    ListServicesData,
    ServerHealthData,
    ServerOperationData,
    ServiceData,
    ServiceHealthData,
    ServiceLogsData,
)
from mlox.application.result import OperationResult
from mlox.project import ProjectWorkspace


def test_operation_result_remains_runtime_compatible_with_dictionary_payloads():
    payload: ListServersData = {"servers": []}

    result = OperationResult[ListServersData](True, 0, "ok", payload)

    assert result.data == {"servers": []}
    assert result.data.get("servers") == []
    assert bool(result)


def test_public_workspace_operations_declare_payload_contracts():
    expected = {
        "set_secret_manager": OperationResult[None],
        "use_embedded_secret_manager": OperationResult[None],
        "list_servers": OperationResult[ListServersData],
        "add_server": OperationResult[BundleData],
        "setup_server": OperationResult[ServerOperationData],
        "check_server_health": OperationResult[ServerHealthData],
        "teardown_server": OperationResult[None],
        "save_server_key": OperationResult[None],
        "list_services": OperationResult[ListServicesData],
        "add_service": OperationResult[ServiceData],
        "setup_service": OperationResult[ServiceData],
        "check_service_health": OperationResult[ServiceHealthData],
        "teardown_service": OperationResult[ServiceData],
        "start_service": OperationResult[ServiceData],
        "restart_service": OperationResult[ServiceData],
        "stop_service": OperationResult[ServiceData],
        "rename_service": OperationResult[ServiceData],
        "service_logs": OperationResult[ServiceLogsData],
        "list_models": OperationResult[ListModelsData],
        "deploy_model": OperationResult[ServiceData],
        "list_server_configs": OperationResult[ListConfigsData],
        "list_service_configs": OperationResult[ListConfigsData],
    }

    actual = {
        name: get_type_hints(getattr(ProjectWorkspace, name))["return"]
        for name in expected
    }

    assert actual == expected


def test_serializable_list_payloads_have_stable_top_level_keys():
    assert ListServersData.__required_keys__ == frozenset({"servers"})
    assert ListServicesData.__required_keys__ == frozenset({"services"})
    assert ListModelsData.__required_keys__ == frozenset({"models"})
    assert ListConfigsData.__required_keys__ == frozenset({"configs"})
