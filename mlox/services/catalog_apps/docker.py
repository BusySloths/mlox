"""Shared Docker Compose runtime for curated, packaged applications."""
from __future__ import annotations

import ipaddress
import re
import hashlib
from dataclasses import dataclass, field

import yaml

from mlox.service import AbstractService, AbstractWebUIService, AbstractSecretManagerService, ServiceCapability
from mlox.services.mlflow_gateway.k3s_managed_tls import _valid_hostname, _validate_certificate


def _option(value: str, default: str = "") -> str:
    value = str(value or "").strip()
    return default if re.fullmatch(r"\$\{[A-Za-z_][A-Za-z0-9_]*\}", value) else value or default


@dataclass
class CatalogAppDockerService(AbstractService, AbstractWebUIService):
    """Run one curated app and a socket-free Traefik instance per installation."""

    capabilities = {ServiceCapability.WEB_UI}
    port: str | int
    app_port: int
    password: str = field(default="", repr=False)
    tls_mode: str = "self-signed"
    tls_secret_manager_uuid: str = ""
    tls_secret_name: str = ""
    hostname: str = ""
    acme_email: str = ""
    imap_server: str = ""
    smtp_server: str = ""
    imap_port: str = "143"
    smtp_port: str = "587"

    def __post_init__(self):
        super().__post_init__()
        self.tls_mode = _option(self.tls_mode, "self-signed")
        self.tls_secret_manager_uuid = _option(self.tls_secret_manager_uuid)
        self.tls_secret_name = _option(self.tls_secret_name)
        self.hostname = _option(self.hostname)
        self.acme_email = _option(self.acme_email)
        self.imap_server = _option(self.imap_server)
        self.smtp_server = _option(self.smtp_server)
        self.imap_port = _option(self.imap_port, "143")
        self.smtp_port = _option(self.smtp_port, "587")
        self.password = _option(self.password)
        if not re.search(rf"-{int(self.port)}-[0-9a-f]{{32}}$", self.target_path):
            self.target_path = f"{self.target_path}-{self.port}-{self.uuid}"
        self.service_ports["Web UI"] = int(self.port)
        self.compose_service_names = {"Application": f"mlox-app-{self.port}", "Traefik": f"mlox-app-proxy-{self.port}"}

    def _load_secret(self):
        if not self.tls_secret_manager_uuid or not self.tls_secret_name:
            raise ValueError("TLS requires a secret-manager service UUID and secret name.")
        provider = self.get_dependent_service(self.tls_secret_manager_uuid, required_type=AbstractSecretManagerService, required_capabilities={ServiceCapability.SECRET_MANAGER})
        if not isinstance(provider, AbstractSecretManagerService):
            raise ValueError("TLS secret-manager service is unavailable.")
        secret = provider.get_secret_manager(self._service_lookup).load_secret(self.tls_secret_name)
        if not isinstance(secret, dict):
            raise ValueError("The TLS secret must be an object.")
        return secret

    def _configuration(self, conn):
        mode = self.tls_mode
        if mode not in {"self-signed", "managed", "letsencrypt-cloudflare"}:
            raise ValueError("TLS mode must be self-signed, managed, or letsencrypt-cloudflare.")
        hostname = self.hostname.lower().rstrip(".")
        secret = self._load_secret() if mode != "self-signed" else {}
        files = {}
        if mode == "managed":
            hostname = str(secret.get("tls.hostname", "")).strip().lower().rstrip(".")
            cert, key = secret.get("tls.crt"), secret.get("tls.key")
            if not _valid_hostname(hostname) or not isinstance(cert, str) or not isinstance(key, str):
                raise ValueError("Managed TLS needs tls.hostname, tls.crt and tls.key in the secret.")
            _validate_certificate(cert, key, hostname)
            files.update({"tls.crt": cert, "tls.key": key})
        if mode == "letsencrypt-cloudflare":
            token = secret.get("cloudflare.api_token")
            if not _valid_hostname(hostname) or not self.acme_email or not isinstance(token, str) or not token.strip() or "\n" in token:
                raise ValueError("Let's Encrypt requires a hostname, email, and cloudflare.api_token secret.")
            files["cloudflare-token"] = token.strip()
        host = hostname or str(conn.host)
        try:
            ipaddress.ip_address(host)
        except ValueError:
            if not re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9.-]*[A-Za-z0-9])?", host):
                raise ValueError("Invalid public hostname.")
        dynamic = {"http": {"routers": {"app": {"rule": "Host(`" + host + "`)", "entryPoints": ["websecure"], "service": "app", "tls": {}}}, "services": {"app": {"loadBalancer": {"servers": [{"url": f"http://app:{self.app_port}"}]}}}}}
        if mode == "managed":
            dynamic["tls"] = {"certificates": [{"certFile": "/config/tls.crt", "keyFile": "/config/tls.key"}]}
        if mode == "letsencrypt-cloudflare":
            dynamic["http"]["routers"]["app"]["tls"] = {"certResolver": "letsencrypt"}
        config = yaml.safe_load(self.resolve_asset(self.template).read_text())
        proxy = {"image": "traefik:v3.3.7", "container_name": f"mlox-app-proxy-{self.port}", "restart": "unless-stopped", "command": ["--providers.file.filename=/config/dynamic.yaml", "--entrypoints.websecure.address=:443"], "ports": [f"{self.port}:443"], "volumes": ["./dynamic.yaml:/config/dynamic.yaml:ro"]}
        if mode == "managed":
            proxy["volumes"] += ["./tls.crt:/config/tls.crt:ro", "./tls.key:/config/tls.key:ro"]
        if mode == "letsencrypt-cloudflare":
            proxy["command"] += ["--certificatesresolvers.letsencrypt.acme.dnschallenge.provider=cloudflare", f"--certificatesresolvers.letsencrypt.acme.email={self.acme_email}", "--certificatesresolvers.letsencrypt.acme.storage=/acme/acme.json"]
            proxy["environment"] = {"CF_DNS_API_TOKEN_FILE": "/config/cloudflare-token"}
            proxy["volumes"] += ["./cloudflare-token:/config/cloudflare-token:ro", "./acme:/acme"]
        config["services"]["app"]["container_name"] = f"mlox-app-{self.port}"
        for service_name, service in config["services"].items():
            if service_name != "app":
                service["container_name"] = f"mlox-app-{self.port}-{service_name}"
        config["services"]["traefik"] = proxy
        return host, config, dynamic, files

    def setup(self, conn):
        if "roundcube" in self.service_config_id:
            for address in (self.imap_server, self.smtp_server):
                if not re.fullmatch(r"(?:tls|ssl)://[A-Za-z0-9.-]+", address):
                    raise ValueError("Roundcube requires IMAP and SMTP hosts prefixed with tls:// or ssl://.")
            if any(not p.isdigit() or not 1 <= int(p) <= 65535 for p in (self.imap_port, self.smtp_port)):
                raise ValueError("Roundcube mail ports must be between 1 and 65535.")
        host, config, dynamic, files = self._configuration(conn)
        self.compose_service_names = {name: service["container_name"] for name, service in config["services"].items()}
        self.exec.fs_create_dir(conn, self.target_path)
        self.exec.fs_set_permissions(conn, self.target_path, "700")
        self.exec.fs_write_file(conn, f"{self.target_path}/{self.target_docker_script}", yaml.safe_dump(config, sort_keys=False))
        self.exec.fs_write_file(conn, f"{self.target_path}/dynamic.yaml", yaml.safe_dump(dynamic, sort_keys=False))
        # The generated credential is persisted in the encrypted MLOX project and
        # written only to this private deployment directory.
        secret_hash = hashlib.sha256(self.password.encode()).hexdigest()
        env = f"APP_PASSWORD={secret_hash}\nIMAP_SERVER={self.imap_server}\nSMTP_SERVER={self.smtp_server}\nIMAP_PORT={self.imap_port}\nSMTP_PORT={self.smtp_port}\nROUNDCUBE_KEY={secret_hash[:24]}\n"
        self.exec.fs_write_file(conn, f"{self.target_path}/{self.target_docker_env}", env)
        self.exec.fs_set_permissions(conn, f"{self.target_path}/{self.target_docker_env}", "600")
        for name, content in files.items():
            path = f"{self.target_path}/{name}"
            self.exec.fs_write_file(conn, path, content)
            self.exec.fs_set_permissions(conn, path, "600")
        if self.tls_mode == "letsencrypt-cloudflare":
            self.exec.fs_create_dir(conn, f"{self.target_path}/acme")
            self.exec.fs_set_permissions(conn, f"{self.target_path}/acme", "700")
        self.service_urls["Web UI"] = f"https://{host}:{self.port}"
        self.state = "starting"

    def spin_up(self, conn):
        return self.compose_up(conn)

    def spin_down(self, conn):
        self.exec.docker_down(conn, f"{self.target_path}/{self.target_docker_script}", f"{self.target_path}/{self.target_docker_env}", remove_volumes=False)
        self.state = "stopped"
        return True

    def teardown(self, conn):
        # Retain both volumes and deployment files for data recovery.
        self.spin_down(conn)
        self.state = "un-initialized"

    def check(self, conn):
        states = {name: self.exec.docker_service_state(conn, container) or "unknown" for name, container in self.compose_service_names.items()}
        if states and all(str(s).lower() == "running" for s in states.values()):
            status = "running"
        elif states and all(str(s).lower() in {"exited", "stopped", "dead"} for s in states.values()):
            status = "stopped"
        else:
            status = "unknown"
        self.state = status
        return {"status": status, "services": states}

    def get_secrets(self):
        return {}
