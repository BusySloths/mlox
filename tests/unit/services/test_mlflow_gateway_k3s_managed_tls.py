from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

from mlox.config import load_all_service_configs
from mlox.service import AbstractSecretManagerService
from mlox.services.mlflow_gateway.k3s_managed_tls import (
    MLFlowGatewayManagedTlsK3sService,
)
from mlox.utils import dataclass_to_dict, dict_to_dataclass


def _tls_material(hostname: str = "gateway.example.org") -> dict[str, str]:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = issuer = x509.Name(
        [x509.NameAttribute(NameOID.COMMON_NAME, hostname)]
    )
    now = datetime.now(timezone.utc)
    certificate = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=1))
        .not_valid_after(now + timedelta(days=30))
        .add_extension(x509.SubjectAlternativeName([x509.DNSName(hostname)]), False)
        .sign(key, hashes.SHA256())
    )
    return {
        "tls.crt": certificate.public_bytes(serialization.Encoding.PEM).decode(),
        "tls.key": key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        ).decode(),
    }


class _SecretManager:
    def __init__(self, value) -> None:
        self.value = value
        self.loaded: list[str] = []

    def load_secret(self, name: str):
        self.loaded.append(name)
        return self.value


class _SecretManagerService(AbstractSecretManagerService):
    def __init__(self, uuid: str, manager: _SecretManager) -> None:
        self.uuid = uuid
        self.manager = manager
        self.context = None

    def get_secret_manager(self, infra):
        self.context = infra
        return self.manager


class _Lookup:
    def __init__(self, service) -> None:
        self.service = service

    def get_service_by_uuid(self, service_uuid: str):
        return self.service if self.service.uuid == service_uuid else None

    def get_service_by_name(self, service_name: str):
        return None


class _Executor:
    def __init__(self) -> None:
        self.calls: list[tuple] = []
        self.files: dict[str, str] = {}
        self.apply_result = "configured"
        self.namespace_result = "namespace configured"
        self.tls_result = "secret configured"

    def _record(self, name, *args, **kwargs):
        self.calls.append((name, args, kwargs))

    def k8s_ensure_namespace(self, conn, namespace, **kwargs):
        self._record("k8s_ensure_namespace", namespace, **kwargs)
        return self.namespace_result

    def k8s_apply_tls_secret(self, conn, name, **kwargs):
        self._record("k8s_apply_tls_secret", name, **kwargs)
        return self.tls_result

    def fs_create_dir(self, conn, path):
        self._record("fs_create_dir", path)

    def fs_write_file(self, conn, path, content):
        self._record("fs_write_file", path, content)
        self.files[path] = content

    def k8s_apply_manifest(self, conn, path, **kwargs):
        self._record("k8s_apply_manifest", path, **kwargs)
        return self.apply_result

    def execute(self, conn, command, **kwargs):
        self._record("execute", command, **kwargs)
        if "rollout status" in command:
            return "deployment successfully rolled out"
        raise AssertionError(f"Unexpected command: {command}")


@pytest.fixture
def managed_gateway(tmp_path: Path):
    serve_script = tmp_path / "serve.py"
    serve_script.write_text("print('gateway')\n", encoding="utf-8")
    tls = _tls_material()
    manager = _SecretManager(tls)
    manager_service = _SecretManagerService("manager-uuid", manager)
    lookup = _Lookup(manager_service)
    service = MLFlowGatewayManagedTlsK3sService(
        name="MLflow Gateway TLS",
        service_config_id="mlflow-gateway-3.8.1-k3s-managed-tls",
        template="unused",
        target_path="/tmp/mlflow-gateway-tls",
        dockerfile="unused",
        serve_script=str(serve_script),
        start_script="unused",
        port=30433,
        tracking_uri="https://mlflow.example.test",
        tracking_user="tracking-user",
        tracking_pw="tracking-password",
        requirements_txt="pydantic==2.0.0",
        user="gateway-user",
        pw="gateway-password",
        tls_hostname="gateway.example.org",
        tls_secret_manager_uuid="manager-uuid",
        tls_secret_name="gateway-tls",
    )
    service.bind_service_lookup(lookup)
    service.exec = _Executor()
    return service, tls, manager, manager_service, lookup


def test_renders_host_tls_ingress_without_pem(managed_gateway) -> None:
    service, tls, _, _, _ = managed_gateway

    manifest = service._render_gateway_manifest()
    documents = list(yaml.safe_load_all(manifest))
    ingress = next(item for item in documents if item.get("kind") == "Ingress")

    assert len(documents) == 9
    assert ingress["spec"]["rules"][0]["host"] == "gateway.example.org"
    assert ingress["spec"]["tls"] == [
        {
            "hosts": ["gateway.example.org"],
            "secretName": service.tls_kubernetes_secret_name,
        }
    ]
    assert tls["tls.crt"] not in manifest
    assert tls["tls.key"] not in manifest


def test_setup_resolves_secret_through_bound_lookup_and_applies_tls_first(
    managed_gateway,
) -> None:
    service, tls, manager, manager_service, lookup = managed_gateway

    service.setup(SimpleNamespace(host="10.0.0.4"))

    call_names = [call[0] for call in service.exec.calls]
    assert call_names.index("k8s_ensure_namespace") < call_names.index(
        "k8s_apply_tls_secret"
    ) < call_names.index("k8s_apply_manifest")
    tls_call = next(call for call in service.exec.calls if call[0] == "k8s_apply_tls_secret")
    assert tls_call[2]["certificate"] == tls["tls.crt"]
    assert tls_call[2]["private_key"] == tls["tls.key"]
    assert manager.loaded == ["gateway-tls"]
    assert manager_service.context is lookup
    assert service.service_url == (
        f"https://gateway.example.org{service.ingress_path}"
    )
    assert tls["tls.crt"] not in service.exec.files[service.manifest_path]
    assert tls["tls.key"] not in service.exec.files[service.manifest_path]


def test_validation_failure_happens_before_cluster_mutation(managed_gateway) -> None:
    service, _, manager, _, _ = managed_gateway
    manager.value = {"tls.crt": "not a certificate", "tls.key": "not a key"}

    with pytest.raises(ValueError, match="valid PEM"):
        service.setup(SimpleNamespace(host="10.0.0.4"))

    assert service.exec.calls == []


def test_missing_secret_manager_happens_before_cluster_mutation(
    managed_gateway,
) -> None:
    service, _, _, _, _ = managed_gateway
    service.tls_secret_manager_uuid = "missing-manager"

    with pytest.raises(ValueError, match="not an available secret manager"):
        service.setup(SimpleNamespace(host="10.0.0.4"))

    assert service.exec.calls == []


def test_rejects_mismatched_key_and_uncovered_hostname(managed_gateway) -> None:
    service, tls, manager, _, _ = managed_gateway
    manager.value = {**tls, "tls.key": _tls_material()["tls.key"]}
    with pytest.raises(ValueError, match="do not match"):
        service.setup(SimpleNamespace(host="10.0.0.4"))
    assert service.exec.calls == []

    manager.value = tls
    service.tls_hostname = "other.example.org"
    with pytest.raises(ValueError, match="does not cover"):
        service.setup(SimpleNamespace(host="10.0.0.4"))
    assert service.exec.calls == []


def test_persistence_round_trip_contains_references_only(managed_gateway) -> None:
    service, tls, _, _, _ = managed_gateway
    service.exec = service.__dataclass_fields__["exec"].default_factory()

    payload = dataclass_to_dict(service)
    serialized = json.dumps(payload)
    restored = dict_to_dataclass(payload)

    assert isinstance(restored, MLFlowGatewayManagedTlsK3sService)
    assert restored.tls_hostname == "gateway.example.org"
    assert restored.tls_secret_manager_uuid == "manager-uuid"
    assert restored.tls_secret_name == "gateway-tls"
    assert tls["tls.crt"] not in serialized
    assert tls["tls.key"] not in serialized


def test_catalog_instantiates_managed_tls_variant() -> None:
    configs = {config.id: config for config in load_all_service_configs()}
    config = configs["mlflow-gateway-3.8.1-k3s-managed-tls"]
    service = config.instantiate_service(
        {
            "${MLOX_STACKS_PATH}": str(Path(__file__).parents[3] / "mlox" / "services"),
            "${MLOX_USER_HOME}": "/tmp/mlox",
            "${MLOX_AUTO_PORT_REST}": "30433",
            "${TRACKING_URI}": "https://mlflow.example",
            "${TRACKING_USER}": "user",
            "${TRACKING_PW}": "password",
            "${GATEWAY_REQUIREMENTS_TXT}": "",
            "${GATEWAY_CACHE_MAX_MODELS}": "10",
            "${GATEWAY_CACHE_TTL_DAYS}": "10",
            "${MLOX_AUTO_USER}": "gateway-user",
            "${MLOX_AUTO_PW}": "gateway-password",
            "${MODEL_REGISTRY_UUID}": "registry-uuid",
            "${TLS_HOSTNAME}": "gateway.example.org",
            "${TLS_SECRET_MANAGER_UUID}": "manager-uuid",
            "${TLS_SECRET_NAME}": "gateway-tls",
        }
    )

    assert isinstance(service, MLFlowGatewayManagedTlsK3sService)
    assert service.tls_secret_manager_uuid == "manager-uuid"
    assert service.tls_secret_name == "gateway-tls"
