"""Small, secret-safe client for InfluxDB 3 Core.

The client deliberately uses the documented HTTP v3 endpoints rather than
making a process-wide dependency on a vendor SDK.  It is suitable for managed
runtimes and for external clients that receive only an encrypted MLOX
secret-manager access keyfile.
"""

from __future__ import annotations

import base64
import os

from dataclasses import dataclass, field
from typing import Any, Mapping

import requests

from mlox.secret_manager import load_secret_manager_from_env, load_secret_manager_from_keyfile


INFLUX_URL_ENV = "MLOX_INFLUX_URL"
INFLUX_TOKEN_ENV = "MLOX_INFLUX_TOKEN"
INFLUX_DATABASE_ENV = "MLOX_INFLUX_DATABASE"
INFLUX_CERTIFICATE_B64_ENV = "MLOX_INFLUX_CERTIFICATE_B64"
INFLUX_SERVICE_ENV = "MLOX_INFLUX_SERVICE"


@dataclass(repr=False)
class InfluxClient:
    """Bounded InfluxDB 3 client whose representation never includes a token."""

    url: str
    token: str = field(repr=False)
    database: str = "telemetry"
    certificate: bytes | None = field(default=None, repr=False)
    timeout_seconds: float = 10.0

    def __post_init__(self) -> None:
        self.url = self.url.rstrip("/")
        if not self.url.startswith(("https://", "http://")):
            raise ValueError("Influx URL must use http or https.")
        if not self.token.strip():
            raise ValueError("Influx token is required.")
        if not self.database.strip():
            raise ValueError("Influx database is required.")

    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None) -> "InfluxClient | None":
        """Create a client from a managed runtime binding, or return ``None``.

        A complete direct binding wins.  Otherwise a service reference is
        resolved through the standard encrypted secret-manager keyfile env.
        """
        env = os.environ if environ is None else environ
        url = str(env.get(INFLUX_URL_ENV, "")).strip()
        token = str(env.get(INFLUX_TOKEN_ENV, "")).strip()
        database = str(env.get(INFLUX_DATABASE_ENV, "telemetry")).strip()
        if url or token:
            if not url or not token:
                raise ValueError("Influx runtime binding requires both URL and token.")
            certificate = _certificate_from_env(env)
            return cls(url=url, token=token, database=database, certificate=certificate)
        service_name = str(env.get(INFLUX_SERVICE_ENV, "")).strip()
        if not service_name:
            return None
        manager = load_secret_manager_from_env(environ=env)
        if manager is None:
            raise ValueError("Influx service reference requires a secret-manager binding.")
        return cls.from_secret_manager(manager, service_name)

    @classmethod
    def from_keyfile(
        cls, service_name: str, encrypted_access_keyfile: str, access_password: str
    ) -> "InfluxClient":
        manager = load_secret_manager_from_keyfile(encrypted_access_keyfile, access_password)
        if manager is None:
            raise ValueError("Could not load secret manager from access keyfile.")
        return cls.from_secret_manager(manager, service_name)

    @classmethod
    def from_secret_manager(cls, manager: Any, service_name: str) -> "InfluxClient":
        name_map = manager.load_secret("MLOX_SERVICE_NAME_UUID_MAP")
        if not isinstance(name_map, dict) or service_name not in name_map:
            raise ValueError("Influx service is not available in the secret manager.")
        service_secret = manager.load_secret(str(name_map[service_name]))
        if not isinstance(service_secret, dict):
            raise ValueError("Influx service connection is unavailable.")
        connection = service_secret.get("influx_connection", service_secret)
        if not isinstance(connection, dict):
            raise ValueError("Influx service connection is invalid.")
        return cls(
            url=str(connection.get("url") or ""),
            token=str(connection.get("token") or ""),
            database=str(connection.get("database") or "telemetry"),
            certificate=_as_bytes(connection.get("certificate")),
        )

    def _request(self, method: str, path: str, **kwargs: Any) -> requests.Response:
        headers = dict(kwargs.pop("headers", {}))
        headers["Authorization"] = f"Bearer {self.token}"
        response = requests.request(
            method, f"{self.url}{path}", headers=headers,
            timeout=min(max(self.timeout_seconds, 1.0), 30.0),
            verify=self.certificate or True, **kwargs,
        )
        response.raise_for_status()
        return response

    def health(self) -> dict[str, Any]:
        response = self._request("GET", "/health")
        try:
            return dict(response.json())
        except ValueError:
            return {"status": response.text.strip() or "ok"}

    def query(self, sql: str, *, max_rows: int = 500) -> list[dict[str, Any]]:
        """Run a SELECT-only bounded SQL query and return at most ``max_rows`` rows."""
        statement = sql.strip().rstrip(";")
        if not statement.lower().startswith("select"):
            raise ValueError("Only SELECT queries are permitted.")
        limit = min(max(int(max_rows), 1), 1000)
        if " limit " not in statement.lower():
            statement = f"{statement} LIMIT {limit}"
        response = self._request(
            "POST", "/api/v3/query_sql",
            json={"db": self.database, "q": statement, "format": "json"},
        )
        payload = response.json()
        rows = payload if isinstance(payload, list) else payload.get("data", [])
        return [dict(row) for row in rows[:limit] if isinstance(row, dict)]

    def write_line_protocol(self, line_protocol: str) -> None:
        if not line_protocol.strip():
            raise ValueError("Line protocol is required.")
        self._request(
            "POST", "/api/v3/write_lp", params={"db": self.database},
            data=line_protocol.encode("utf-8"), headers={"Content-Type": "text/plain"},
        )


def _as_bytes(value: Any) -> bytes | None:
    if value is None or value == "":
        return None
    return value.encode("utf-8") if isinstance(value, str) else bytes(value)


def _certificate_from_env(env: Mapping[str, str]) -> bytes | None:
    encoded = str(env.get(INFLUX_CERTIFICATE_B64_ENV, "")).strip()
    if not encoded:
        return None
    try:
        return base64.b64decode(encoded, validate=True)
    except (ValueError, TypeError) as exc:
        raise ValueError("Invalid base64 Influx certificate content.") from exc
