"""End-to-end catalog deployments on the disposable Multipass Docker server."""
from __future__ import annotations

import shlex
import time
from datetime import datetime, timedelta, timezone

import pytest
import requests
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

from mlox.config import load_service_config_by_id
from mlox.infra import Bundle, Infrastructure
from tests.integration.helpers import add_service, log_compose_diagnostics, remove_service

pytestmark = pytest.mark.integration


@pytest.fixture(params=[
    ("catalog-app-memos-0.31.0-docker", "app", "/var/opt/memos"),
    ("catalog-app-etherpad-2.6.1-docker", "db", "/var/lib/postgresql/data"),
    ("catalog-app-wikijs-2.5.306-docker", "db", "/var/lib/postgresql/data"),
    ("catalog-app-roundcube-1.6.11-docker", "app", "/var/roundcube/db"),
], ids=["memos", "etherpad", "wikijs", "roundcube"])
def deployed_app(request, ubuntu_docker_server):
    config_id, volume_service, volume_path = request.param
    config = load_service_config_by_id(config_id)
    assert config is not None
    infra = Infrastructure()
    bundle = Bundle(name=ubuntu_docker_server.ip, server=ubuntu_docker_server)
    infra.bundles.append(bundle)
    added = add_service(infra, ubuntu_docker_server.ip, config, {
        "${APP_IMAP_SERVER}": "ssl://mail.example.org",
        "${APP_IMAP_PORT}": "993",
        "${APP_SMTP_SERVER}": "tls://mail.example.org",
    })
    assert added is not None
    service = added.services[-1]
    try:
        with ubuntu_docker_server.get_server_connection() as conn:
            service.setup(conn)
            service.spin_up(conn)
        yield bundle, infra, service, volume_service, volume_path
    finally:
        try:
            # The fixture owns this Compose project and the dedicated test VM.
            with ubuntu_docker_server.get_server_connection() as conn:
                service.exec.docker_down(conn, f"{service.target_path}/{service.target_docker_script}", f"{service.target_path}/{service.target_docker_env}", remove_volumes=True)
        finally:
            if infra.get_service(service.name):
                remove_service(infra, service.name)


def _wait_for_https(service, bundle, *, timeout=300):
    deadline = time.monotonic() + timeout
    last = None
    while time.monotonic() < deadline:
        try:
            response = requests.get(service.service_urls["Web UI"], verify=False, timeout=5, allow_redirects=False)
            if response.status_code in (200, 301, 302, 303, 307, 308):
                return response
            last = f"HTTP {response.status_code}"
        except requests.RequestException as exc:
            last = str(exc)
        time.sleep(3)
    log_compose_diagnostics(service, bundle)
    pytest.fail(f"Application did not become reachable via HTTPS: {last}")


def _in_container(conn, service, service_name, command):
    name = shlex.quote(service.compose_service_names[service_name])
    return conn.sudo(f"docker exec --user 0 {name} sh -c {shlex.quote(command)}", hide=True, warn=False, pty=False, in_stream=False, timeout=30)


def test_app_https_and_persistent_data_after_stop_restart_and_removal(deployed_app):
    bundle, infra, service, volume_service, volume_path = deployed_app
    _wait_for_https(service, bundle)
    marker = f"{volume_path}/mlox-integration-persistence"
    with bundle.server.get_server_connection() as conn:
        _in_container(conn, service, volume_service, f"printf mlox-persisted > {shlex.quote(marker)}")
        service.spin_down(conn)
        service.spin_up(conn)
    _wait_for_https(service, bundle)
    with bundle.server.get_server_connection() as conn:
        result = _in_container(conn, service, volume_service, f"cat {shlex.quote(marker)}")
        assert result.stdout.strip() == "mlox-persisted"
        assert service.check(conn)["status"] == "running"

    # The application-level removal path must leave the named volumes intact.
    assert remove_service(infra, service.name).success
    with bundle.server.get_server_connection() as conn:
        service.spin_up(conn)
    _wait_for_https(service, bundle)
    with bundle.server.get_server_connection() as conn:
        result = _in_container(conn, service, volume_service, f"cat {shlex.quote(marker)}")
        assert result.stdout.strip() == "mlox-persisted"


def _certificate(hostname):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    now = datetime.now(timezone.utc)
    subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, hostname)])
    cert = (x509.CertificateBuilder().subject_name(subject).issuer_name(subject)
            .public_key(key.public_key()).serial_number(x509.random_serial_number())
            .not_valid_before(now - timedelta(minutes=1)).not_valid_after(now + timedelta(days=1))
            .add_extension(x509.SubjectAlternativeName([x509.DNSName(hostname)]), False)
            .sign(key, hashes.SHA256()))
    return {"tls.hostname": hostname,
            "tls.crt": cert.public_bytes(serialization.Encoding.PEM).decode(),
            "tls.key": key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()).decode()}


def test_managed_certificate_is_served_by_traefik(ubuntu_docker_server, monkeypatch):
    config = load_service_config_by_id("catalog-app-memos-0.31.0-docker")
    infra = Infrastructure()
    bundle = Bundle(name=ubuntu_docker_server.ip, server=ubuntu_docker_server)
    infra.bundles.append(bundle)
    added = add_service(infra, ubuntu_docker_server.ip, config, {
        "${APP_TLS_MODE}": "managed",
        "${APP_TLS_SECRET_MANAGER_UUID}": "test-manager",
        "${APP_TLS_SECRET_NAME}": "test-cert",
    })
    assert added is not None
    service = added.services[-1]
    hostname = "catalog-app.example.org"
    material = _certificate(hostname)
    monkeypatch.setattr(service, "_load_secret", lambda: material)
    try:
        with bundle.server.get_server_connection() as conn:
            service.setup(conn)
            service.spin_up(conn)
        deadline = time.monotonic() + 300
        last = ""
        while time.monotonic() < deadline:
            with bundle.server.get_server_connection() as conn:
                command = (f"curl --silent --show-error --noproxy '*' --output /dev/null "
                           f"--write-out '%{{http_code}}' --cacert {shlex.quote(service.target_path + '/tls.crt')} "
                           f"--resolve {hostname}:{service.port}:127.0.0.1 https://{hostname}:{service.port}/")
                result = conn.run(command, hide=True, warn=True, pty=False, in_stream=False, timeout=10)
                last = result.stdout.strip() or result.stderr.strip()
                if result.ok and last in {"200", "301", "302", "303", "307", "308"}:
                    break
            time.sleep(3)
        else:
            log_compose_diagnostics(service, bundle)
            pytest.fail(f"Managed certificate HTTPS request failed: {last}")
    finally:
        with ubuntu_docker_server.get_server_connection() as conn:
            service.exec.docker_down(conn, f"{service.target_path}/{service.target_docker_script}", f"{service.target_path}/{service.target_docker_env}", remove_volumes=True)
        if infra.get_service(service.name):
            remove_service(infra, service.name)
