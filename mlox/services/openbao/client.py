"""Client implementation for interacting with an OpenBao server."""

from __future__ import annotations

import json
import logging
import ssl
from dataclasses import dataclass, field
from typing import Any, Dict
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from mlox.secret_manager import AbstractSecretManager

logger = logging.getLogger(__name__)


@dataclass
class OpenBaoSecretManager(AbstractSecretManager):
    """Interact with an OpenBao (Vault-compatible) secrets server."""

    address: str
    token: str
    mount_path: str = "secret"
    timeout: float = 10.0
    verify_tls: bool = False
    unseal_keys: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.address.startswith("http://") and not self.address.startswith(
            "https://"
        ):
            # Keep bare addresses usable for internal/bootstrap calls.
            self.address = f"http://{self.address}"
        self.address = self.address.rstrip("/")
        self.mount_path = self.mount_path.strip("/") or "secret"

    # ------------------------------------------------------------------
    # Helper utilities
    # ------------------------------------------------------------------
    def _request(
        self,
        method: str,
        path: str,
        *,
        data: Dict[str, Any] | None = None,
        params: Dict[str, Any] | None = None,
        expected_status: tuple[int, ...] = (200, 204),
        token: str | None = None,
        include_token: bool = True,
    ) -> Dict[str, Any]:
        """Execute an HTTP request against the OpenBao API.

        The client is self-contained: every operation only needs an OpenBao
        address, token, mount path, and TLS preference. Calls such as userpass
        login can opt out of the token header with ``include_token=False``.
        """

        url = f"{self.address}{path}"
        if params:
            query = urlencode(params)
            if query:
                url = f"{url}?{query}"

        payload_bytes = None
        headers: Dict[str, str] = {}
        selected_token = self.token if token is None else token
        if include_token and selected_token:
            headers["X-Vault-Token"] = selected_token
        if data is not None:
            payload_bytes = json.dumps(data).encode("utf-8")
            headers["Content-Type"] = "application/json"

        request = Request(url=url, method=method, headers=headers, data=payload_bytes)

        open_kwargs: Dict[str, Any] = {"timeout": self.timeout}
        if url.startswith("https://"):
            context = (
                ssl.create_default_context()
                if self.verify_tls
                else ssl._create_unverified_context()
            )
            open_kwargs["context"] = context

        try:
            with urlopen(  # nosec B310 - controlled URL
                request, **open_kwargs
            ) as response:
                status = response.status
                body_bytes = response.read()
                body = body_bytes.decode("utf-8") if body_bytes else ""
        except HTTPError as exc:
            status = exc.code
            body_bytes = exc.read() if exc.fp else b""
            body = body_bytes.decode("utf-8") if body_bytes else ""
            if status not in expected_status:
                raise
        except URLError as exc:  # pragma: no cover - network failure path
            raise ConnectionError(
                f"Failed to reach OpenBao at {url}: {exc.reason}"
            ) from exc

        if status not in expected_status:
            raise RuntimeError(f"Unexpected response {status} from OpenBao for {path}")

        if not body:
            return {}

        try:
            return json.loads(body)
        except json.JSONDecodeError:
            return {"raw": body}

    @staticmethod
    def _stringify_duration(value: str | int | float | None) -> str | None:
        """Coerce numeric durations into Vault-friendly seconds strings."""
        if value is None:
            return None
        if isinstance(value, (int, float)):
            return f"{int(value)}s"
        return str(value)

    # ------------------------------------------------------------------
    # AbstractSecretManager interface
    # ------------------------------------------------------------------
    def is_working(self) -> bool:
        try:
            health = self.seal_status()
        except Exception as exc:  # pragma: no cover - defensive logging path
            logger.warning("OpenBao health check failed: %s", exc)
            return False
        return bool(health.get("initialized", False)) and not bool(
            health.get("sealed", True)
        )

    def init_status(self) -> bool:
        response = self._request("GET", "/v1/sys/init")
        return bool(response.get("initialized", False))

    def initialize(self, secret_shares: int, secret_threshold: int) -> Dict[str, Any]:
        return self._request(
            "POST",
            "/v1/sys/init",
            data={
                "secret_shares": int(secret_shares),
                "secret_threshold": int(secret_threshold),
            },
        )

    def seal_status(self) -> Dict[str, Any]:
        return self._request(
            "GET",
            "/v1/sys/health",
            expected_status=(200, 429, 472, 473, 501, 503),
        )

    def unseal(self, key: str) -> Dict[str, Any]:
        return self._request(
            "POST",
            "/v1/sys/unseal",
            data={"key": key},
        )

    def enable_kv_v2(self, mount_path: str) -> None:
        mount = mount_path.strip("/") or self.mount_path
        response = self._request(
            "POST",
            f"/v1/sys/mounts/{mount}",
            data={"type": "kv", "options": {"version": "2"}},
            expected_status=(200, 204, 400),
        )
        errors = response.get("errors", [])
        if errors and not any("path is already in use" in str(err) for err in errors):
            raise RuntimeError(f"Could not enable OpenBao KV v2 mount {mount}: {errors}")

    def list_mounts(self) -> Dict[str, Any]:
        """Return enabled secrets engines keyed by mount path."""

        return self._request("GET", "/v1/sys/mounts").get("data", {})

    def ensure_kv_v2(self, mount_path: str | None = None) -> None:
        """Ensure a KV v2 secrets engine exists at ``mount_path``."""

        mount = (mount_path or self.mount_path).strip("/") or self.mount_path
        mounts = self.list_mounts()
        mount_key = f"{mount}/"
        existing = mounts.get(mount_key) or mounts.get(mount)
        if existing:
            options = existing.get("options", {}) if isinstance(existing, dict) else {}
            if existing.get("type") == "kv" and str(options.get("version")) == "2":
                return
        self.enable_kv_v2(mount)

    def write_policy(self, name: str, policy: str) -> None:
        """Create or update an OpenBao policy."""

        self._request(
            "POST",
            f"/v1/sys/policy/{name}",
            data={"policy": policy},
            expected_status=(200, 204),
        )

    def read_policy(self, name: str) -> Dict[str, Any] | None:
        """Read a policy or return ``None`` if it does not exist."""

        try:
            return self._request("GET", f"/v1/sys/policy/{name}")
        except HTTPError as exc:
            if exc.code == 404:
                return None
            raise

    def list_auth_methods(self) -> Dict[str, Any]:
        """Return enabled auth methods keyed by mount path."""

        return self._request("GET", "/v1/sys/auth").get("data", {})

    def enable_auth_method(self, path: str, auth_type: str) -> None:
        """Enable an auth method if it is not already enabled."""

        mount = path.strip("/")
        response = self._request(
            "POST",
            f"/v1/sys/auth/{mount}",
            data={"type": auth_type},
            expected_status=(200, 204, 400),
        )
        errors = response.get("errors", [])
        if errors and not any("path is already in use" in str(err) for err in errors):
            raise RuntimeError(
                f"Could not enable OpenBao auth method {auth_type} at {mount}: {errors}"
            )

    def ensure_userpass_auth(self, path: str = "userpass") -> None:
        """Ensure userpass auth is enabled at ``path``."""

        mount = path.strip("/") or "userpass"
        auth_methods = self.list_auth_methods()
        existing = auth_methods.get(f"{mount}/") or auth_methods.get(mount)
        if isinstance(existing, dict) and existing.get("type") == "userpass":
            return
        self.enable_auth_method(mount, "userpass")

    def create_or_update_userpass_user(
        self,
        username: str,
        password: str,
        *,
        policies: list[str],
        ttl: str | int | None = "8h",
        max_ttl: str | int | None = "24h",
        path: str = "userpass",
    ) -> None:
        """Create or update a userpass user for UI login."""

        payload: Dict[str, Any] = {
            "password": password,
            "token_policies": policies,
        }
        if ttl is not None:
            payload["token_ttl"] = self._stringify_duration(ttl)
        if max_ttl is not None:
            payload["token_max_ttl"] = self._stringify_duration(max_ttl)
        self._request(
            "POST",
            f"/v1/auth/{path.strip('/')}/users/{username}",
            data=payload,
            expected_status=(200, 204),
        )

    def login_userpass(
        self, username: str, password: str, *, path: str = "userpass"
    ) -> Dict[str, Any]:
        """Authenticate with userpass and return the OpenBao ``auth`` block."""

        response = self._request(
            "POST",
            f"/v1/auth/{path.strip('/')}/login/{username}",
            data={"password": password},
            include_token=False,
        )
        auth = response.get("auth", {})
        if not auth.get("client_token"):
            raise RuntimeError("OpenBao userpass login did not return a client token.")
        return auth

    def enable_file_audit(self, path: str = "/openbao/logs/audit.log") -> None:
        response = self._request(
            "PUT",
            "/v1/sys/audit/file",
            data={"type": "file", "options": {"file_path": path}},
            expected_status=(200, 204, 400),
        )
        errors = response.get("errors", [])
        if errors and not any(
            "path is already in use" in str(err) or "already exists" in str(err)
            for err in errors
        ):
            raise RuntimeError(f"Could not enable OpenBao file audit: {errors}")

    def list_secrets(self, keys_only: bool = False) -> Dict[str, Any]:
        path = f"/v1/{self.mount_path}/metadata"
        try:
            response = self._request("GET", path, params={"list": "true"})
        except HTTPError as exc:
            if exc.code == 404:
                return {}
            raise

        keys = response.get("data", {}).get("keys", [])
        results: Dict[str, Any] = {}
        for raw_key in keys:
            key = raw_key.rstrip("/")
            if keys_only:
                results[key] = None
            else:
                secret = self.load_secret(key)
                if secret is not None:
                    results[key] = secret
        return results

    def save_secret(self, name: str, my_secret: Dict | str) -> None:
        payload: Dict[str, Any]
        if isinstance(my_secret, str):
            try:
                payload = json.loads(my_secret)
            except json.JSONDecodeError:
                payload = {"value": my_secret}
        else:
            payload = my_secret
        path = f"/v1/{self.mount_path}/data/{name}"
        self._request("POST", path, data={"data": payload}, expected_status=(200, 204))

    def load_secret(self, name: str) -> Dict | str | None:
        path = f"/v1/{self.mount_path}/data/{name}"
        try:
            response = self._request("GET", path)
        except HTTPError as exc:
            if exc.code == 404:
                return None
            raise
        data = response.get("data", {}).get("data", None)
        return data

    @classmethod
    def instantiate_secret_manager(
        cls, info: Dict[str, Any]
    ) -> "OpenBaoSecretManager | None":
        address = info.get("address")
        token = info.get("token")
        if not address or not token:
            logger.error(
                "OpenBaoSecretManager requires 'address' and 'token' entries. Provided keys: %s",
                list(info.keys()),
            )
            return None
        mount_path = info.get("mount_path", "secret")
        timeout = float(info.get("timeout", 10.0))
        verify_raw = info.get("verify_tls", False)
        if isinstance(verify_raw, str):
            verify_tls = verify_raw.strip().lower() in {"1", "true", "yes", "on"}
        else:
            verify_tls = bool(verify_raw)
        return cls(
            address=address,
            token=token,
            mount_path=mount_path,
            timeout=timeout,
            verify_tls=verify_tls,
            unseal_keys=list(info.get("unseal_keys", [])),
        )

    def create_token(
        self,
        ttl: str | int,
        *,
        policies: list[str] | None = None,
        renewable: bool | None = None,
        explicit_max_ttl: str | int | None = None,
        num_uses: int | None = None,
        no_default_policy: bool | None = None,
        period: str | int | None = None,
        metadata: Dict[str, str] | None = None,
        role_name: str | None = None,
    ) -> Dict[str, Any]:
        """Create a new scoped child token using the manager's root/admin token."""

        duration = self._stringify_duration(ttl)
        if not duration:
            raise ValueError("A TTL must be provided when creating a token.")

        payload: Dict[str, Any] = {"ttl": duration}
        if policies is not None:
            payload["policies"] = policies
        if renewable is not None:
            payload["renewable"] = renewable
        if explicit_max_ttl is not None:
            payload["explicit_max_ttl"] = self._stringify_duration(explicit_max_ttl)
        if num_uses is not None:
            payload["num_uses"] = num_uses
        if no_default_policy is not None:
            payload["no_default_policy"] = no_default_policy
        if period is not None:
            payload["period"] = self._stringify_duration(period)
        if metadata:
            payload["meta"] = metadata

        path = "/v1/auth/token/create"
        if role_name:
            path = f"{path}/{role_name}"

        response = self._request("POST", path, data=payload)
        auth = response.get("auth", {})
        client_token = auth.get("client_token")
        if not client_token:
            raise RuntimeError("OpenBao did not return a client token.")
        return auth

    def lookup_self(self) -> Dict[str, Any]:
        """Lookup the current token and return the OpenBao data block."""

        return self._request("GET", "/v1/auth/token/lookup-self").get("data", {})

    def lookup_token(self, token: str) -> Dict[str, Any]:
        """Lookup an arbitrary token using the current token's privileges."""

        return self._request(
            "POST", "/v1/auth/token/lookup", data={"token": token}
        ).get("data", {})

    def renew_self(self, increment: str | int | None = None) -> Dict[str, Any]:
        """Renew the current token and return the OpenBao auth block."""

        payload: Dict[str, Any] = {}
        if increment is not None:
            payload["increment"] = self._stringify_duration(increment)
        response = self._request(
            "POST", "/v1/auth/token/renew-self", data=payload
        )
        auth = response.get("auth", {})
        if not auth:
            raise RuntimeError("OpenBao did not return token renewal information.")
        return auth

    def renew_token(
        self, token: str, increment: str | int | None = None
    ) -> Dict[str, Any]:
        """Renew an arbitrary token using the current token's privileges."""

        payload: Dict[str, Any] = {"token": token}
        if increment is not None:
            payload["increment"] = self._stringify_duration(increment)
        response = self._request("POST", "/v1/auth/token/renew", data=payload)
        auth = response.get("auth", {})
        if not auth:
            raise RuntimeError("OpenBao did not return token renewal information.")
        return auth

    def get_access_secrets(self) -> Dict[str, Any] | None:
        return {
            "address": self.address,
            "token": self.token,
            "mount_path": self.mount_path,
            "verify_tls": self.verify_tls,
            "unseal_keys": list(self.unseal_keys),
        }
