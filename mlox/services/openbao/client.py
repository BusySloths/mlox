"""Client implementation for interacting with an OpenBao server."""

from __future__ import annotations

import json
import logging
import ssl
from dataclasses import dataclass
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

    def __post_init__(self) -> None:
        if not self.address.startswith("http://") and not self.address.startswith("https://"):
            # Default to http because the dev server exposed by the stack does not use TLS
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
    ) -> Dict[str, Any]:
        """Execute an HTTP request against the OpenBao API."""

        url = f"{self.address}{path}"
        if params:
            query = urlencode(params)
            if query:
                url = f"{url}?{query}"

        payload_bytes = None
        headers = {"X-Vault-Token": self.token}
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
            raise ConnectionError(f"Failed to reach OpenBao at {url}: {exc.reason}") from exc

        if status not in expected_status:
            raise RuntimeError(f"Unexpected response {status} from OpenBao for {path}")

        if not body:
            return {}

        try:
            return json.loads(body)
        except json.JSONDecodeError:
            return {"raw": body}

    # ------------------------------------------------------------------
    # AbstractSecretManager interface
    # ------------------------------------------------------------------
    def is_working(self) -> bool:
        try:
            health = self._request("GET", "/v1/sys/health")
        except Exception as exc:  # pragma: no cover - defensive logging path
            logger.warning("OpenBao health check failed: %s", exc)
            return False
        return bool(health.get("initialized", False))

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
        )

    def get_access_secrets(self) -> Dict[str, Any] | None:
        return {
            "address": self.address,
            "token": self.token,
            "mount_path": self.mount_path,
            "verify_tls": self.verify_tls,
        }
