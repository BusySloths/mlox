"""Exercise live routing to an unchanged catalog app on a disposable VM."""
import time

import pytest
import requests

from mlox.config import load_service_config_by_id
from mlox.infra import Bundle, Infrastructure
from tests.integration.helpers import add_service, log_compose_diagnostics, remove_service

pytestmark = pytest.mark.integration


def _wait(url, *, host=None, expected=200, timeout=240):
    deadline = time.monotonic() + timeout
    last = None
    while time.monotonic() < deadline:
        try:
            last = requests.get(url, headers={'Host': host} if host else {}, verify=False, timeout=5, allow_redirects=False)
            if last.status_code == expected:
                return last
        except requests.RequestException as exc:
            last = exc
        time.sleep(2)
    pytest.fail(f'{url} did not return {expected}: {last}')


def test_live_route_to_existing_self_signed_app(ubuntu_docker_server):
    server = ubuntu_docker_server
    infra = Infrastructure()
    bundle = Bundle(name=server.ip, server=server)
    infra.bundles.append(bundle)
    app = reverse_proxy = None
    try:
        config = load_service_config_by_id('catalog-app-memos-0.31.0-docker')
        assert add_service(infra, server.ip, config, {})
        app = bundle.services[-1]
        with server.get_server_connection() as conn:
            app.setup(conn)
            app.spin_up(conn)
        _wait(app.service_urls['Web UI'])
        app_url = app.service_urls['Web UI']
        app_path = app.target_path

        config = load_service_config_by_id('docker-proxy-1-docker')
        assert add_service(infra, server.ip, config, {})
        reverse_proxy = bundle.services[-1]
        with server.get_server_connection() as conn:
            reverse_proxy.setup(conn)
            reverse_proxy.spin_up(conn)
            reverse_proxy.add_route(conn, hostname='memos.example.org',
                                    backend=f'https://host.docker.internal:{app.port}',
                                    backend_host=server.ip, insecure_backend=True)
        _wait(f'https://{server.ip}/', host='memos.example.org')
        assert app.service_urls['Web UI'] == app_url
        assert app.target_path == app_path
        _wait(app_url)
        with server.get_server_connection() as conn:
            reverse_proxy.remove_route(conn, hostname='memos.example.org')
        _wait(f'https://{server.ip}/', host='memos.example.org', expected=404)
        _wait(app_url)
    except Exception:
        if reverse_proxy:
            log_compose_diagnostics(reverse_proxy, bundle)
        if app:
            log_compose_diagnostics(app, bundle)
        raise
    finally:
        for service in (reverse_proxy, app):
            if service is None:
                continue
            with server.get_server_connection() as conn:
                service.exec.docker_down(conn, f'{service.target_path}/{service.target_docker_script}', f'{service.target_path}/{service.target_docker_env}', remove_volumes=True)
            if infra.get_service(service.name):
                remove_service(infra, service.name)


def test_gateway_reports_occupied_port_without_stopping_existing_container(ubuntu_docker_server):
    import shlex
    import uuid

    server = ubuntu_docker_server
    infra = Infrastructure()
    bundle = Bundle(name=server.ip, server=server)
    infra.bundles.append(bundle)
    listener = f'mlox-port80-test-{uuid.uuid4().hex[:12]}'
    service = None
    try:
        with server.get_server_connection() as conn:
            conn.sudo(
                f'docker run -d --name {shlex.quote(listener)} -p 80:80 '
                'traefik:v3.3.7 --entrypoints.web.address=:80',
                hide=True, warn=False, pty=False, in_stream=False,
            )
        config = load_service_config_by_id('docker-proxy-1.0.0-docker')
        assert add_service(infra, server.ip, config, {})
        service = bundle.services[-1]
        with server.get_server_connection() as conn:
            service.setup(conn)
            with pytest.raises(RuntimeError, match=listener):
                service.spin_up(conn)
            state = conn.sudo(
                f"docker inspect --format '{{{{.State.Running}}}}' {shlex.quote(listener)}",
                hide=True, warn=False, pty=False, in_stream=False,
            )
            assert state.stdout.strip() == 'true'
    finally:
        if service and infra.get_service(service.name):
            remove_service(infra, service.name)
        with server.get_server_connection() as conn:
            conn.sudo(f'docker rm -f {shlex.quote(listener)}', hide=True, warn=True, pty=False, in_stream=False)
