from __future__ import annotations

from dataclasses import dataclass

import pytest

from mlox.service import (
    AbstractHealthService,
    AbstractSecretManagerService,
    AbstractService,
    ServiceCapability,
    service_health_payload,
)
from mlox.secret_manager import AbstractSecretManager


class _Exec:
    def __init__(self):
        self.history = [{"action": "one", "status": "ok"}]
        self.calls = []

    def docker_up(self, conn, compose, env):
        self.calls.append(("up", compose, env))

    def docker_down(self, conn, compose, remove_volumes=False):
        self.calls.append(("down", compose, remove_volumes))

    def docker_restart(self, conn, compose, env):
        self.calls.append(("restart", compose, env))

    def docker_all_service_states(self, conn):
        return {
            "proj_api_1": {"Status": "running"},
            "db": {"State": "exited"},
        }

    def docker_service_state(self, conn, service):
        return "fallback"

    def docker_service_log_tails(self, conn, service, tail=200):
        return f"logs:{service}:{tail}"

    def fs_create_dir(self, conn, path):
        self.calls.append(("mkdir", path))

    def fs_touch(self, conn, path):
        self.calls.append(("touch", path))

    def fs_write_file(self, conn, path, content):
        self.calls.append(("write", path, str(content)[:30]))

    def fs_set_permissions(self, conn, path, mode):
        self.calls.append(("chmod", path, mode))


@dataclass
class _Service(AbstractService):
    def setup(self, conn):
        return None

    def teardown(self, conn):
        return None

    def check(self, conn):
        return {}

    def get_secrets(self):
        return {}


class _SecretManager(AbstractSecretManager):
    def is_working(self):
        return True

    def list_secrets(self, keys_only=False):
        return {}

    def save_secret(self, name, my_secret):
        return None

    def load_secret(self, name):
        return None

    @classmethod
    def instantiate_secret_manager(cls, info):
        return cls()

    def get_access_secrets(self):
        return {}


@dataclass
class _SecretProvider(_Service, AbstractSecretManagerService):
    capabilities = {ServiceCapability.SECRET_MANAGER}
    calls: int = 0

    def get_secret_manager(self, infra):
        self.calls += 1
        return _SecretManager()


@dataclass
class _TelemetryProvider(_Service):
    capabilities = {ServiceCapability.OBSERVABILITY}

    def get_secrets(self):
        return {
            "otel_client_connection": {
                "collector_url": "https://otel.example:4317",
                "protocol": "otlp_grpc",
            }
        }


@dataclass
class _BindingService(_Service):
    applied: list = None

    def __post_init__(self):
        super().__post_init__()
        self.applied = []

    def _apply_secret_manager_binding(self, conn, *, manager_uuid, manager):
        self.applied.append(("bind-secret-manager", manager_uuid))

    def _remove_secret_manager_binding(self, conn):
        self.applied.append(("unbind-secret-manager",))

    def _apply_telemetry_binding(self, conn, *, telemetry_uuid, connection):
        self.applied.append(("bind-telemetry", telemetry_uuid, connection))

    def _remove_telemetry_binding(self, conn):
        self.applied.append(("unbind-telemetry",))


def _svc():
    svc = _Service(
        name="svc", service_config_id="cfg", template="t", target_path="/tmp/svc"
    )
    svc.exec = _Exec()
    svc.compose_service_names = {"api": "api", "db": "db"}
    return svc


def test_get_dependent_service_can_require_type_and_capabilities():
    service = _svc()
    dependency = _svc()
    dependency.capabilities = {ServiceCapability.SECRET_MANAGER, "web_ui"}
    lookup = type(
        "Lookup",
        (),
        {
            "get_service_by_uuid": lambda self, uuid: dependency,
            "get_service_by_name": lambda self, name: None,
        },
    )()
    service.bind_service_lookup(lookup)

    assert service.get_dependent_service(
        dependency.uuid,
        required_type=_Service,
        required_capabilities={ServiceCapability.SECRET_MANAGER, "web_ui"},
    ) is dependency
    assert service.get_dependent_service(
        dependency.uuid, required_type=_HealthService
    ) is None
    assert service.get_dependent_service(
        dependency.uuid, required_capabilities={ServiceCapability.DATABASE}
    ) is None


def test_secret_manager_and_telemetry_bindings_are_independent_and_reversible():
    service = _BindingService(
        name="consumer",
        service_config_id="cfg",
        template="t",
        target_path="/tmp/consumer",
    )
    secret_provider = _SecretProvider(
        name="secrets",
        service_config_id="secrets",
        template="t",
        target_path="/tmp/secrets",
    )
    telemetry_provider = _TelemetryProvider(
        name="telemetry",
        service_config_id="telemetry",
        template="t",
        target_path="/tmp/telemetry",
    )
    providers = {
        secret_provider.uuid: secret_provider,
        telemetry_provider.uuid: telemetry_provider,
    }
    lookup = type(
        "Lookup",
        (),
        {
            "get_service_by_uuid": lambda self, uuid: providers.get(uuid),
            "get_service_by_name": lambda self, name: None,
        },
    )()
    service.bind_service_lookup(lookup)
    service.state = "running"

    service.bind_secret_manager(secret_provider.uuid, conn=object())
    service.bind_telemetry(telemetry_provider.uuid, conn=object())

    assert service.secret_manager_uuid == secret_provider.uuid
    assert service.telemetry_uuid == telemetry_provider.uuid
    assert service.get_bound_secret_manager() is service.get_bound_secret_manager()
    assert secret_provider.calls == 1
    assert service.get_bound_telemetry_secrets()["collector_url"].endswith("4317")

    service.unbind_telemetry(conn=object())
    assert service.telemetry_uuid is None
    assert service.secret_manager_uuid == secret_provider.uuid

    service.unbind_secret_manager(conn=object())
    assert service.secret_manager_uuid is None
    assert service.applied[-2:] == [
        ("unbind-telemetry",),
        ("unbind-secret-manager",),
    ]


def test_failed_live_binding_restores_previous_provider_uuid():
    service = _Service(
        name="consumer",
        service_config_id="cfg",
        template="t",
        target_path="/tmp/consumer",
        telemetry_uuid="previous-telemetry",
    )
    telemetry_provider = _TelemetryProvider(
        name="telemetry",
        service_config_id="telemetry",
        template="t",
        target_path="/tmp/telemetry",
    )
    service.bind_service_lookup(
        type(
            "Lookup",
            (),
            {
                "get_service_by_uuid": lambda self, uuid: telemetry_provider,
                "get_service_by_name": lambda self, name: None,
            },
        )()
    )
    service.state = "running"

    with pytest.raises(RuntimeError, match="does not support telemetry bindings"):
        service.bind_telemetry(telemetry_provider.uuid, conn=object())

    assert service.telemetry_uuid == "previous-telemetry"


def test_compose_up_restart_and_down_update_state():
    svc = _svc()

    assert svc.compose_up(conn=object()) is True
    assert svc.state == "running"
    assert svc.exec.calls[-1] == ("up", "/tmp/svc/docker-compose.yaml", "/tmp/svc/service.env")

    svc.state = "unknown"
    assert svc.compose_restart(conn=object()) is True
    assert svc.state == "running"
    assert svc.exec.calls[-1] == (
        "restart",
        "/tmp/svc/docker-compose.yaml",
        "/tmp/svc/service.env",
    )

    assert svc.compose_down(conn=object(), remove_volumes=True) is True
    assert svc.state == "stopped"


def test_service_restart_prefers_compose_restart_for_compose_services():
    svc = _svc()

    assert svc.restart(conn=object()) is True

    assert svc.exec.calls[-1] == (
        "restart",
        "/tmp/svc/docker-compose.yaml",
        "/tmp/svc/service.env",
    )


def test_compose_service_status_and_logs_paths():
    svc = _svc()

    statuses = svc.compose_service_status(conn=object())
    assert statuses["db"] == "exited"

    assert svc.compose_service_log_tail(conn=object(), label="api", tail=10).startswith(
        "logs:"
    )
    assert svc.compose_service_log_tail(conn=object(), label="missing") == "Not found"
    assert svc.log_labels() == ["api", "db"]
    assert svc.service_log_tail(conn=object(), label="api", tail=10).startswith("logs:")


def test_dump_state_writes_debug_files():
    svc = _svc()

    svc.dump_state(conn=object())

    write_calls = [c for c in svc.exec.calls if c[0] == "write"]
    assert any("start.sh" in c[1] for c in write_calls)
    assert any("service-state.json" in c[1] for c in write_calls)


def test_health_capability_is_optional_for_services():
    svc = _svc()

    assert ServiceCapability.HEALTH.value == "health"
    assert ServiceCapability.HEALTH not in getattr(svc, "capabilities", set())
    assert not hasattr(svc, "get_health")


@dataclass
class _HealthService(_Service, AbstractHealthService):
    capabilities = {ServiceCapability.HEALTH}

    def check(self, conn):
        self.state = "running"
        return {"status": "running", "detail": "probe ok"}

    def get_health(self, conn):
        return service_health_payload(self, self.check(conn))


def test_health_service_normalizes_probe_payload():
    svc = _HealthService(
        name="svc",
        service_config_id="cfg",
        template="t",
        target_path="/tmp/svc",
    )

    health = svc.get_health(conn=object())

    assert health == {
        "status": "running",
        "detail": "probe ok",
        "state": "running",
        "healthy": True,
    }
