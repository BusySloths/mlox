from contextlib import nullcontext
from types import SimpleNamespace

import pytest

from tests.integration import conftest as integration
from tests.integration.helpers import log_compose_diagnostics


@pytest.mark.parametrize(
    "status,no_checks,expected_calls",
    [
        ({"status": "stopped"}, False, 1),
        ({"status": "running"}, False, 0),
        ({"status": "stopped"}, True, 0),
    ],
)
def test_readiness_only_collects_diagnostics_after_failed_checks(
    monkeypatch, status, no_checks, expected_calls
):
    calls = []
    service, bundle = SimpleNamespace(), object()
    monkeypatch.setattr(integration.time, "sleep", lambda _: None)
    monkeypatch.setattr(
        integration, "log_compose_diagnostics", lambda *args: calls.append(args)
    )

    result = integration.wait_for_service_ready(
        service, bundle, check_fn=lambda: status, retries=1, interval=0,
        no_checks=no_checks,
    )

    assert len(calls) == expected_calls
    assert result == ({"status": "unknown"} if no_checks else status)


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
    fixture = integration.ubuntu_docker_server.__wrapped__(
        {"ip": server.ip, "name": "test-vm"}
    )

    assert next(fixture) is server
    with pytest.raises(StopIteration):
        next(fixture)

    assert len(calls) == 2
    assert all(command == "docker volume ls -q" for command, _ in calls)
    assert all(options["warn"] is False for _, options in calls)
