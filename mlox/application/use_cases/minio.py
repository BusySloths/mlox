"""MinIO bucket inspection and coordinated TLS certificate replacement."""
from __future__ import annotations

import ipaddress
import shlex
import tempfile
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlsplit
from uuid import uuid4

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

from mlox.application.result import OperationResult
from mlox.execution.base import TaskGroup


def certificate_details(pem: str) -> str:
    if not pem:
        return "No certificate recorded in the project."
    try:
        cert = x509.load_pem_x509_certificate(pem.encode())
        expires = cert.not_valid_after_utc
        days = (expires - datetime.now(timezone.utc)).days
        return f"Expires {expires:%Y-%m-%d %H:%M UTC} ({days} days remaining)"
    except (ValueError, TypeError):
        return "The project certificate could not be parsed."


def list_buckets(infra, service) -> OperationResult:
    try:
        with service.get_storage(infra) as storage:
            buckets = storage.list_buckets()
        return OperationResult(True, 0, "Buckets loaded.", {"buckets": buckets})
    except Exception as exc:
        return OperationResult(False, 1, f"Could not load buckets: {exc}")


def list_objects(infra, service, bucket: str) -> OperationResult:
    try:
        with service.get_storage(infra) as storage:
            objects = storage.list_keys(bucket)
        return OperationResult(True, 0, "Objects loaded.", {"objects": objects})
    except Exception as exc:
        return OperationResult(False, 1, f"Could not load objects: {exc}")


def renew_certificate(infra, bundle, service, workspace=None) -> OperationResult:
    """Replace the TLS pair, verify the endpoint, and restore on failure.

    Secret manager snapshots are deliberately refreshed separately by the user.
    """
    if bundle is None or getattr(bundle, "server", None) is None:
        return OperationResult(False, 1, "The MinIO server is unavailable.")
    host = urlsplit(service.service_url).hostname
    if not host:
        return OperationResult(False, 1, "The MinIO endpoint has no hostname.")
    try:
        address = ipaddress.ip_address(host)
        san = x509.IPAddress(address)
    except ValueError:
        san = x509.DNSName(host)
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    now = datetime.now(timezone.utc)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, host)])
    cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name)
            .public_key(key.public_key()).serial_number(x509.random_serial_number())
            .not_valid_before(now - timedelta(minutes=5))
            .not_valid_after(now + timedelta(days=3650))
            .add_extension(x509.SubjectAlternativeName([san]), critical=False)
            .sign(key, hashes.SHA256()))
    pem = cert.public_bytes(serialization.Encoding.PEM).decode()
    private_key = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.TraditionalOpenSSL, serialization.NoEncryption())
    stage = f"{service.target_path}/.tls-rotation-{uuid4().hex}"
    qstage = shlex.quote(stage)
    qtarget = shlex.quote(service.target_path)
    executor = service.exec
    old_certificate = service.certificate
    installed = False

    def remote(conn, command):
        result = executor._run_task(conn, group=TaskGroup.SECURITY_ASSETS, command=command)
        if result is None or "MLOX_TLS_OK" not in result:
            raise RuntimeError("Remote certificate operation failed; see execution history.")

    def restart(conn):
        result = executor.docker_restart(conn, f"{service.target_path}/{service.target_docker_script}",
                                         f"{service.target_path}/{service.target_docker_env}", force_recreate=True)
        if result is None:
            raise RuntimeError("MinIO container recreation failed.")

    try:
        with bundle.server.get_server_connection() as conn:
            remote(conn, f"umask 077; mkdir {qstage} && echo MLOX_TLS_OK")
            with tempfile.TemporaryDirectory(prefix="mlox-minio-tls-") as tmp:
                cert_file, key_file = Path(tmp) / "cert.pem", Path(tmp) / "key.pem"
                cert_file.write_text(pem, encoding="utf-8")
                key_file.write_bytes(private_key)
                key_file.chmod(0o600)
                executor.fs_copy(conn, str(cert_file), f"{stage}/cert.pem")
                executor.fs_copy(conn, str(key_file), f"{stage}/key.pem")
            # Keep backups in a private directory and restore if either installation fails.
            installed = True
            remote(conn, f"set -eu; cd {qtarget}; chmod 600 {qstage}/key.pem; cp -p cert.pem {qstage}/old-cert.pem; cp -p key.pem {qstage}/old-key.pem; rollback() {{ cp -p {qstage}/old-cert.pem cert.pem; cp -p {qstage}/old-key.pem key.pem; }}; trap rollback EXIT; chmod 600 key.pem; cp {qstage}/cert.pem cert.pem; cp {qstage}/key.pem key.pem; trap - EXIT; echo MLOX_TLS_OK")
            try:
                restart(conn)
                service.certificate = pem
                for attempt in range(10):
                    try:
                        with service.get_storage(infra) as storage:
                            storage.list_buckets()
                        break
                    except Exception:
                        if attempt == 9:
                            raise
                        time.sleep(1)
                if workspace is not None:
                    workspace.commit()
            except Exception:
                service.certificate = old_certificate
                remote(conn, f"set -eu; cd {qtarget}; cp -p {qstage}/old-cert.pem cert.pem; cp -p {qstage}/old-key.pem key.pem; echo MLOX_TLS_OK")
                restart(conn)
                installed = False
                raise
    except Exception as exc:
        detail = " The new files may still be installed; inspect the server and its private rotation backup." if installed else ""
        return OperationResult(False, 1, f"Certificate renewal failed: {exc}.{detail}")
    return OperationResult(True, 0, "Certificate renewed and verified. Collect service secrets in every manager used by clients, then reconnect clients.")
