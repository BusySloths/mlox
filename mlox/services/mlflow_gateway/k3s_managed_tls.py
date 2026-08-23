"""k3s MLflow Gateway variant using secret-manager-backed TLS."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import serialization
from passlib.hash import apr_md5_crypt

from mlox.service import AbstractSecretManagerService, ServiceCapability
from mlox.services.mlflow_gateway.docker import _resolved_setting, _resolved_text
from mlox.services.mlflow_gateway.k3s import MLFlowGatewayK3sService

logger = logging.getLogger(__name__)


@dataclass
class MLFlowGatewayManagedTlsK3sService(MLFlowGatewayK3sService):
    """Expose the gateway through k3s Traefik with externally managed TLS."""

    tls_secret_manager_uuid: str = ""
    tls_secret_name: str = ""
    tls_kubernetes_secret_name: str = field(init=False)

    def __post_init__(self) -> None:
        super().__post_init__()
        # Runtime-only: the hostname is loaded from the referenced secret and is
        # intentionally excluded from persisted service state.
        self._tls_hostname = ""
        self._tls_material: tuple[str, str] | None = None
        self.tls_kubernetes_secret_name = f"mlflow-gateway-tls-{self.gateway_id}"

    def _load_and_validate_tls_material(self) -> tuple[str, str]:
        if not self.tls_secret_manager_uuid:
            raise ValueError("A TLS secret-manager service is required.")
        if not self.tls_secret_name:
            raise ValueError("A TLS secret name is required.")

        manager_service = self.get_dependent_service(
            self.tls_secret_manager_uuid,
            required_type=AbstractSecretManagerService,
            required_capabilities={ServiceCapability.SECRET_MANAGER},
        )
        if not isinstance(manager_service, AbstractSecretManagerService):
            raise ValueError(
                f"Service {self.tls_secret_manager_uuid} is not an available secret manager."
            )
        manager = manager_service.get_secret_manager(self._service_lookup)
        secret = manager.load_secret(self.tls_secret_name)
        if not isinstance(secret, dict):
            raise ValueError(
                "The TLS secret must be an object with tls.hostname, tls.crt, and tls.key."
            )
        hostname = secret.get("tls.hostname")
        certificate = secret.get("tls.crt")
        private_key = secret.get("tls.key")
        if not isinstance(hostname, str) or not _valid_hostname(
            hostname.strip().rstrip(".").lower()
        ):
            raise ValueError("The TLS secret does not contain a valid tls.hostname.")
        hostname = hostname.strip().rstrip(".").lower()
        if not isinstance(certificate, str) or not certificate.strip():
            raise ValueError("The TLS secret does not contain a non-empty tls.crt.")
        if not isinstance(private_key, str) or not private_key.strip():
            raise ValueError("The TLS secret does not contain a non-empty tls.key.")

        _validate_certificate(certificate, private_key, hostname)
        self._tls_hostname = hostname
        return certificate, private_key

    def _render_gateway_manifest(self) -> str:
        serve_script = Path(self.serve_script).read_text(encoding="utf-8")
        requirements = _resolved_text(self.requirements_txt)
        cache_size = _resolved_setting(self.cache_max_models, "10")
        cache_ttl = _resolved_setting(self.cache_ttl_days, "10")
        password_hash = apr_md5_crypt.hash(self.pw)

        return self.render_template(
            "gateway-managed-tls-manifest.yaml.tmpl",
            {
                "namespace": self.namespace,
                "serve_script_block": self.indent_block(serve_script, 4),
                "requirements_block": self.indent_block(requirements, 4),
                "gateway_user": self.yaml_scalar(self.user),
                "gateway_password": self.yaml_scalar(self.pw),
                "basic_auth_secret": self.basic_auth_secret,
                "basic_auth_user": self.yaml_scalar(f"{self.user}:{password_hash}"),
                "basic_auth_middleware": self.basic_auth_middleware,
                "strip_prefix_middleware": self.strip_prefix_middleware,
                "ingress_name": self.ingress_name,
                "ingress_path": self.yaml_scalar(self.ingress_path),
                "tracking_uri": self.yaml_scalar(self.tracking_uri),
                "tracking_user": self.yaml_scalar(self.tracking_user),
                "tracking_password": self.yaml_scalar(self.tracking_pw),
                "deployment_name": self.deployment_name,
                "container_port": self.container_port,
                "cache_size": self.yaml_scalar(cache_size),
                "cache_ttl": self.yaml_scalar(cache_ttl),
                "service_name": self.service_name,
                "tls_hostname": self.yaml_scalar(self._tls_hostname),
                "tls_secret_name": self.tls_kubernetes_secret_name,
            },
        )

    def setup(self, conn) -> None:
        certificate, private_key = self._load_and_validate_tls_material()
        self._tls_material = (certificate, private_key)
        try:
            super().setup(conn)
            if self.state != "running":
                raise RuntimeError("Failed to apply the MLflow Gateway manifest.")
        except Exception:
            try:
                super().teardown(conn)
            except Exception:
                logger.exception(
                    "Failed to roll back managed-TLS gateway namespace %s.",
                    self.namespace,
                )
            raise
        finally:
            self._tls_material = None

        self.service_url = f"https://{self._tls_hostname}{self.ingress_path}"
        self.service_urls["MLflow Gateway REST API"] = self.service_url

    def _after_manifest_apply(self, conn) -> None:
        if self._tls_material is None:
            raise RuntimeError("TLS material was not prepared for gateway setup.")
        certificate, private_key = self._tls_material
        if (
            self.exec.k8s_apply_tls_secret(
                conn,
                self.tls_kubernetes_secret_name,
                namespace=self.namespace,
                certificate=certificate,
                private_key=private_key,
                kubeconfig=self.kubeconfig,
            )
            is None
        ):
            raise RuntimeError("Failed to apply the MLflow Gateway TLS secret.")


def _valid_hostname(hostname: str) -> bool:
    if not hostname or len(hostname) > 253:
        return False
    labels = hostname.split(".")
    return len(labels) >= 2 and all(
        re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", label)
        for label in labels
    )


def _validate_certificate(certificate_pem: str, private_key_pem: str, hostname: str) -> None:
    try:
        certificates = x509.load_pem_x509_certificates(certificate_pem.encode("utf-8"))
        private_key = serialization.load_pem_private_key(
            private_key_pem.encode("utf-8"), password=None
        )
    except (TypeError, ValueError) as exc:
        raise ValueError("The TLS certificate or private key is not valid PEM.") from exc
    if not certificates:
        raise ValueError("The TLS certificate does not contain a certificate.")
    certificate = certificates[0]

    now = datetime.now(timezone.utc)
    if now < certificate.not_valid_before_utc or now > certificate.not_valid_after_utc:
        raise ValueError("The TLS certificate is not currently valid.")

    public_format = serialization.PublicFormat.SubjectPublicKeyInfo
    certificate_key = certificate.public_key().public_bytes(
        serialization.Encoding.DER, public_format
    )
    private_public_key = private_key.public_key().public_bytes(
        serialization.Encoding.DER, public_format
    )
    if certificate_key != private_public_key:
        raise ValueError("The TLS certificate and private key do not match.")

    try:
        names = certificate.extensions.get_extension_for_class(
            x509.SubjectAlternativeName
        ).value.get_values_for_type(x509.DNSName)
    except x509.ExtensionNotFound:
        names = [
            attribute.value
            for attribute in certificate.subject.get_attributes_for_oid(
                x509.NameOID.COMMON_NAME
            )
        ]
    if not any(_hostname_matches(pattern, hostname) for pattern in names):
        raise ValueError("The TLS certificate does not cover the configured hostname.")


def _hostname_matches(pattern: str, hostname: str) -> bool:
    pattern = pattern.strip().rstrip(".").lower()
    if pattern.startswith("*."):
        suffix = pattern[2:]
        return hostname.endswith(f".{suffix}") and len(hostname.split(".")) == len(
            suffix.split(".")
        ) + 1
    return pattern == hostname
