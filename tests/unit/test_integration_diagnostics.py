from contextlib import nullcontext
import json
from types import SimpleNamespace

import pytest

from tests.integration import conftest as integration
from tests.integration.helpers import log_compose_diagnostics


@pytest.mark.parametrize(
    "status,expected_calls",
    [
        ({"status": "stopped"}, 1),
        ({"status": "running"}, 0),
    ],
)
def test_readiness_only_collects_diagnostics_after_failed_checks(
    monkeypatch, status, expected_calls
):
    calls = []
    service, bundle = SimpleNamespace(), object()
    monkeypatch.setattr(integration.time, "sleep", lambda _: None)
    monkeypatch.setattr(
        integration, "log_compose_diagnostics", lambda *args: calls.append(args)
    )

    result = integration.wait_for_service_ready(
        service, bundle, check_fn=lambda: status, retries=1, interval=0,
    )

    assert len(calls) == expected_calls
    assert result == status


def test_compose_readiness_waits_for_health_and_accepts_completed_initializer(monkeypatch):
    states = iter([
        [{"Name": "app", "State": "created", "ExitCode": 0}],
        [{"Name": "app", "State": "running", "Health": "starting"}],
        [{"Name": "init", "State": "exited", "ExitCode": 0},
         {"Name": "app", "State": "running", "Health": "healthy"}],
    ])
    calls = []

    def sudo(command, **kwargs):
        calls.append((command, kwargs))
        return SimpleNamespace(exited=0, stdout=json.dumps(next(states)))

    conn = SimpleNamespace(sudo=sudo)
    server = SimpleNamespace(backend=["docker"], get_server_connection=lambda: nullcontext(conn))
    service = SimpleNamespace(target_path="/tmp/test stack", target_docker_script="compose.yaml",
                              target_docker_env="service.env", compose_service_names={"app": "app"})
    checks = []
    sleeps = []
    monkeypatch.setattr(integration.time, "sleep", sleeps.append)
    result = integration.wait_for_service_ready(
        service, SimpleNamespace(server=server), retries=3, interval=5,
        check_fn=lambda: checks.append(True) or {"status": "running"},
    )
    assert result["status"] == "running"
    assert sleeps == [5, 5] and len(checks) == 1
    assert "ps --all --format json" in calls[0][0]
    assert all(call[1]["in_stream"] is False for call in calls)


def test_compose_exit_failure_stops_early_and_collects_diagnostics(monkeypatch):
    result = SimpleNamespace(exited=0, stdout='{"Name":"collector","State":"exited","ExitCode":2}')
    conn = SimpleNamespace(sudo=lambda *args, **kwargs: result)
    bundle = SimpleNamespace(server=SimpleNamespace(backend=["docker"], get_server_connection=lambda: nullcontext(conn)))
    service = SimpleNamespace(target_path="/tmp/stack", target_docker_script="compose.yaml",
                              target_docker_env="service.env", compose_service_names={"collector": "collector"})
    diagnostics = []
    monkeypatch.setattr(integration, "log_compose_diagnostics", lambda *args: diagnostics.append(args))
    monkeypatch.setattr(integration.time, "sleep", lambda _: pytest.fail("must not sleep after a crash"))
    status = integration.wait_for_service_ready(service, bundle, retries=5, interval=5)
    assert status["status"] == "failed" and "exit code 2" in status["detail"]
    assert len(diagnostics) == 1


def test_compose_readiness_parses_ndjson_and_reports_starting():
    output = '\n'.join(json.dumps(row) for row in [
        {"Name": "init", "State": "exited", "ExitCode": 0},
        {"Name": "app", "State": "restarting", "ExitCode": 1},
    ])
    conn = SimpleNamespace(sudo=lambda *args, **kwargs: SimpleNamespace(exited=0, stdout=output))
    service = SimpleNamespace(target_path="/tmp/stack", target_docker_script="compose.yaml", target_docker_env="service.env")
    status = integration._compose_readiness(conn, service)
    assert status["status"] == "starting" and "app: restarting" in status["detail"]


def test_compose_inspection_error_is_not_reported_as_ready(monkeypatch):
    conn = SimpleNamespace(sudo=lambda *args, **kwargs: SimpleNamespace(
        exited=1, stdout="", stderr="[sudo] password: Docker daemon unavailable"
    ))
    bundle = SimpleNamespace(server=SimpleNamespace(backend=["docker"], get_server_connection=lambda: nullcontext(conn)))
    service = SimpleNamespace(target_path="/tmp/stack", target_docker_script="compose.yaml",
                              target_docker_env="service.env", compose_service_names={"collector": "collector"})
    diagnostics = []
    monkeypatch.setattr(integration, "log_compose_diagnostics", lambda *args: diagnostics.append(args))
    result = integration.wait_for_service_ready(service, bundle, retries=1, interval=0)
    assert result["status"] == "unknown" and "Docker daemon unavailable" in result["error"]
    assert len(diagnostics) == 1


def test_diagnostics_collect_logs_even_if_container_listing_fails(caplog):
    calls = []

    def sudo(command, **kwargs):
        calls.append((command, kwargs))
        if len(calls) == 1:
            raise RuntimeError("listing unavailable")
        return SimpleNamespace(
            stdout="client version is too old", stderr="", exited=0
        )

    service = SimpleNamespace(
        name="test-service",
        target_path="/tmp/test stack",
        target_docker_script="compose.yaml",
        target_docker_env="service.env",
        compose_service_names={"Proxy": "traefik"},
    )
    bundle = SimpleNamespace(
        server=SimpleNamespace(
            backend=["docker"],
            get_server_connection=lambda: nullcontext(SimpleNamespace(sudo=sudo)),
        )
    )

    log_compose_diagnostics(service, bundle)

    assert len(calls) == 2
    assert "--env-file '/tmp/test stack/service.env'" in calls[1][0]
    assert "-f '/tmp/test stack/compose.yaml' logs --no-color --tail 80" in calls[1][0]
    assert calls[1][1]["timeout"] == 30
    assert "listing unavailable" in caplog.text
    assert "client version is too old" in caplog.text


def test_docker_volume_checks_use_post_setup_login_and_sudo(monkeypatch):
    calls = []

    def sudo(command, **kwargs):
        calls.append((command, kwargs))
        return SimpleNamespace(stdout="baseline-volume\n")

    # Root/password access is disabled by setup. Only the default key login works.
    server = SimpleNamespace(
        ip="192.0.2.1",
        setup=lambda: None,
        get_server_connection=lambda: nullcontext(SimpleNamespace(sudo=sudo)),
    )
    monkeypatch.setattr(integration, "Infrastructure", lambda: object())
    monkeypatch.setattr(integration, "load_config", lambda *args: object())
    monkeypatch.setattr(
        integration, "add_server", lambda *args: SimpleNamespace(server=server)
    )
    monkeypatch.setattr(
        integration, "remove_server", lambda *args: SimpleNamespace(success=True)
    )
    purges = []
    monkeypatch.setattr(integration, "purge_test_docker", lambda *args, **kwargs: purges.append(kwargs))
    fixture = integration.ubuntu_docker_server.__wrapped__(
        {"ip": server.ip, "name": "test-vm"}
    )

    assert next(fixture) is server
    with pytest.raises(StopIteration):
        next(fixture)

    assert purges == [{"remove_running": True}]
    assert len(calls) == 2
    assert all(command == "docker volume ls -q" for command, _ in calls)
    assert all(options["warn"] is False for _, options in calls)


def test_startup_failure_captures_diagnostics_and_still_cleans_up(monkeypatch):
    from tests.integration import helpers

    events = []
    finalizers = []

    def fail_startup(conn):
        raise RuntimeError("port already allocated")

    service = SimpleNamespace(name="failed-service", setup=lambda conn: None, spin_up=fail_startup)
    bundle = SimpleNamespace(server=SimpleNamespace(get_server_connection=lambda: nullcontext(object())))
    monkeypatch.setattr(helpers, "log_compose_diagnostics", lambda *args: events.append("diagnostics"))
    monkeypatch.setattr(helpers, "remove_service", lambda *args: events.append("cleanup") or SimpleNamespace(success=True))
    with pytest.raises(RuntimeError, match="port already allocated"):
        helpers.prepare_service(SimpleNamespace(addfinalizer=finalizers.append), object(), bundle, service)
    assert events == ["diagnostics"]
    assert len(finalizers) == 1
    finalizers[0]()
    assert events == ["diagnostics", "cleanup"]


@pytest.mark.parametrize("remove_running", [False, True])
def test_docker_purge_is_remote_and_preserves_running_services_until_final_cleanup(remove_running):
    from tests.integration.helpers import purge_test_docker

    calls = []

    def sudo(command, **kwargs):
        calls.append((command, kwargs))
        return SimpleNamespace(stdout="abc123\ndef456\n" if command == "docker ps --all --quiet" else "reclaimed")

    server = SimpleNamespace(ip="test-vm", get_server_connection=lambda: nullcontext(SimpleNamespace(sudo=sudo)))
    purge_test_docker(server, remove_running=remove_running)
    commands = [command for command, _ in calls]
    expected = ["docker system prune --all --force --volumes",
                "docker builder prune --all --force", "docker volume prune --all --force"]
    if remove_running:
        expected = ["docker ps --all --quiet", "docker rm --force --volumes abc123 def456"] + expected
    assert commands == expected
    assert all(options["in_stream"] is False and options["warn"] is False for _, options in calls)
