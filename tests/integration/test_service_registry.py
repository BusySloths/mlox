import gzip
import hashlib
import io
import json
import logging
import os
import tarfile
import tempfile
import time
from typing import Dict, Tuple
from urllib.parse import urlparse

import pytest
import requests

from mlox.config import get_stacks_path, load_config
from mlox.infra import Bundle, Infrastructure
from tests.integration.conftest import wait_for_service_ready

pytestmark = pytest.mark.integration

logger = logging.getLogger(__name__)
requests.packages.urllib3.disable_warnings()  # type: ignore[attr-defined]


@pytest.fixture(scope="module")
def install_registry_service(ubuntu_docker_server):
    infra = Infrastructure()
    bundle = Bundle(name=ubuntu_docker_server.ip, server=ubuntu_docker_server)
    infra.bundles.append(bundle)

    config = load_config(get_stacks_path(), "/registry", "mlox.registry.3.yaml")

    bundle_added = infra.add_service(ubuntu_docker_server.ip, config, params={})
    if not bundle_added:
        pytest.skip("Failed to add registry service from config")

    service = bundle_added.services[-1]

    with ubuntu_docker_server.get_server_connection() as conn:
        service.setup(conn)
        service.spin_up(conn)

    wait_for_service_ready(service, bundle, retries=6, interval=20, no_checks=True)

    yield bundle_added, service

    with ubuntu_docker_server.get_server_connection() as conn:
        try:
            service.spin_down(conn)
        except Exception as exc:
            logger.warning("Error during registry spin_down: %s", exc)
        try:
            service.teardown(conn)
        except Exception as exc:
            logger.warning("Error during registry teardown: %s", exc)
    infra.remove_bundle(bundle_added)


def test_registry_service_running(install_registry_service):
    _, service = install_registry_service
    assert service.service_urls.get("Registry")
    assert service.state == "running"


def test_registry_requires_authentication(install_registry_service):
    _, service = install_registry_service
    url = service.service_urls.get("Registry")
    assert url is not None

    response = requests.get(f"{url}/v2/_catalog", verify=False, timeout=15)
    logger.info(
        "Registry unauthenticated access response to _catalog: %s", response.text
    )
    assert response.status_code == 401


def test_registry_allows_authenticated_access(install_registry_service):
    _, service = install_registry_service
    url = service.service_urls.get("Registry")
    assert url is not None

    response = requests.get(
        f"{url}/v2/_catalog",
        verify=False,
        timeout=15,
        auth=(service.username, service.password),
    )
    logger.info("Registry AUTHENTICATED access response to _catalog: %s", response.text)
    assert response.status_code == 200
    payload = response.json()
    assert isinstance(payload.get("repositories"), list)


def _registry_secrets(service) -> Tuple[str, Dict[str, str]]:
    secrets = service.get_secrets().get("registry_credentials", {})
    registry_url = secrets.get("registry_url")
    assert registry_url, "Missing registry URL in secrets"
    assert secrets.get("username"), "Missing registry username in secrets"
    assert secrets.get("password"), "Missing registry password in secrets"
    return registry_url, secrets


def _requests_session(
    secrets: Dict[str, str],
) -> Tuple[requests.Session, str, str | None]:
    registry_url = secrets["registry_url"]
    parsed = urlparse(registry_url)
    base = f"{parsed.scheme}://{parsed.netloc}"

    cert_path: str | None = None
    certificate = secrets.get("certificate")
    if certificate:
        tmp = tempfile.NamedTemporaryFile(mode="w", delete=False)
        tmp.write(certificate)
        tmp.flush()
        cert_path = tmp.name

    session = requests.Session()
    session.auth = (secrets["username"], secrets["password"])
    session.verify = cert_path if cert_path else False
    return session, base, cert_path


def test_registry_secrets_enable_access(install_registry_service):
    _, service = install_registry_service
    registry_url, secrets = _registry_secrets(service)

    session, base, cert_path = _requests_session(secrets)
    try:
        response = session.get(f"{registry_url}/v2/_catalog", timeout=20)
        assert response.status_code == 200
        payload = response.json()
        assert isinstance(payload.get("repositories"), list)
    finally:
        if cert_path:
            try:
                os.unlink(cert_path)
            except OSError:
                pass


def test_registry_push_and_list_image(install_registry_service):
    _, service = install_registry_service
    registry_url, secrets = _registry_secrets(service)
    session, base, cert_path = _requests_session(secrets)

    repository = "mlox/tinycore-integration"
    tag = "latest"
    try:
        layer_bytes, diff_id = _create_layer_bytes()
        config_bytes = _create_config_bytes(diff_id)

        config_digest, config_size = _ensure_blob(
            session, base, repository, config_bytes
        )
        layer_digest, layer_size = _ensure_blob(session, base, repository, layer_bytes)

        manifest = {
            "schemaVersion": 2,
            "mediaType": "application/vnd.docker.distribution.manifest.v2+json",
            "config": {
                "mediaType": "application/vnd.docker.container.image.v1+json",
                "size": config_size,
                "digest": config_digest,
            },
            "layers": [
                {
                    "mediaType": "application/vnd.docker.image.rootfs.diff.tar.gzip",
                    "size": layer_size,
                    "digest": layer_digest,
                }
            ],
        }
        manifest_payload = json.dumps(
            manifest, separators=(",", ":"), sort_keys=True
        ).encode("utf-8")

        manifest_response = session.put(
            f"{registry_url}/v2/{repository}/manifests/{tag}",
            data=manifest_payload,
            headers={
                "Content-Type": "application/vnd.docker.distribution.manifest.v2+json",
                "Accept": "application/vnd.docker.distribution.manifest.v2+json",
            },
            timeout=30,
        )
        assert manifest_response.status_code in (200, 201)

        catalog = session.get(f"{registry_url}/v2/_catalog", timeout=30)
        assert catalog.status_code == 200
        repositories = catalog.json().get("repositories", [])
        assert repository in repositories

        tags_response = session.get(
            f"{registry_url}/v2/{repository}/tags/list",
            timeout=30,
        )
        assert tags_response.status_code == 200
        tags = tags_response.json().get("tags", [])
        assert tag in tags
    finally:
        if cert_path:
            try:
                os.unlink(cert_path)
            except OSError:
                pass


def _create_layer_bytes() -> Tuple[bytes, str]:
    """Create a tiny gzipped tar archive layer and return bytes + diff_id digest."""
    file_content = b"mlox registry integration test layer\n"
    tar_buffer = io.BytesIO()
    with tarfile.open(mode="w", fileobj=tar_buffer) as tar:
        info = tarfile.TarInfo(name="hello.txt")
        info.size = len(file_content)
        info.mtime = int(time.time())
        tar.addfile(info, io.BytesIO(file_content))

    tar_bytes = tar_buffer.getvalue()
    diff_id = f"sha256:{hashlib.sha256(tar_bytes).hexdigest()}"

    gzip_buffer = io.BytesIO()
    with gzip.GzipFile(mode="wb", fileobj=gzip_buffer) as gz:
        gz.write(tar_bytes)

    layer_bytes = gzip_buffer.getvalue()
    return layer_bytes, diff_id


def _create_config_bytes(diff_id: str) -> bytes:
    created = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    config = {
        "created": created,
        "architecture": "amd64",
        "os": "linux",
        "config": {},
        "rootfs": {"type": "layers", "diff_ids": [diff_id]},
        "history": [{"created": created, "created_by": "pytest registry push"}],
    }
    return json.dumps(config, separators=(",", ":"), sort_keys=True).encode("utf-8")


def _ensure_blob(
    session: requests.Session, base: str, repository: str, blob: bytes
) -> Tuple[str, int]:
    digest = f"sha256:{hashlib.sha256(blob).hexdigest()}"
    size = len(blob)
    blob_url = f"{base}/v2/{repository}/blobs/{digest}"

    head_resp = session.head(blob_url, timeout=20)
    if head_resp.status_code == 200:
        return digest, size

    upload_resp = session.post(f"{base}/v2/{repository}/blobs/uploads/", timeout=20)
    upload_resp.raise_for_status()

    location = upload_resp.headers.get("Location")
    if not location:
        raise AssertionError("Registry did not provide upload location header")
    if location.startswith("/"):
        upload_url = f"{base}{location}"
    elif location.startswith("http"):
        upload_url = location
    else:
        upload_url = f"{base}/{location.lstrip('/')}"

    params = {"digest": digest}
    complete_resp = session.put(
        upload_url,
        params=params,
        data=blob,
        headers={"Content-Type": "application/octet-stream"},
        timeout=30,
    )
    if complete_resp.status_code not in (201, 202):
        complete_resp.raise_for_status()

    return digest, size
