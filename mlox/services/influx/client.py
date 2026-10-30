"""Small, secret-safe client for InfluxDB 3 Core.

The client deliberately uses the documented HTTP v3 endpoints rather than
making a process-wide dependency on a vendor SDK.  It is suitable for managed
runtimes and for external clients that receive only an encrypted MLOX
secret-manager access keyfile.
"""

from __future__ import annotations

import base64
import os
from pathlib import Path
from tempfile import TemporaryDirectory

from dataclasses import dataclass, field
from typing import Any, Mapping

import requests

from mlox.secret_manager import load_secret_manager_from_env, load_secret_manager_from_keyfile


INFLUX_URL_ENV = "MLOX_INFLUX_URL"
INFLUX_TOKEN_ENV = "MLOX_INFLUX_TOKEN"
INFLUX_DATABASE_ENV = "MLOX_INFLUX_DATABASE"
INFLUX_CERTIFICATE_B64_ENV = "MLOX_INFLUX_CERTIFICATE_B64"
INFLUX_SERVICE_ENV = "MLOX_INFLUX_SERVICE"
MAX_TELEMETRY_WINDOW_SECONDS = 86_400
MAX_TELEMETRY_ROWS = 500
MAX_METRIC_TABLES = 20


class _BearerAuth(requests.auth.AuthBase):
    """Explicit auth prevents Requests replacing the token with netrc auth."""

    def __init__(self, token: str) -> None:
        self._token = token

    def __call__(self, request):
        request.headers["Authorization"] = f"Bearer {self._token}"
        return request


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
        options = dict(
            headers=headers, timeout=min(max(self.timeout_seconds, 1.0), 30.0),
            auth=_BearerAuth(self.token),
            **kwargs,
        )
        if self.certificate:
            # Requests expects a CA bundle filename, not PEM bytes. Close the
            # file before opening it through Requests (also works on Windows),
            # and keep it available until the response has been downloaded.
            with TemporaryDirectory(prefix="mlox-influx-ca-") as directory:
                ca_path = Path(directory) / "ca.pem"
                ca_path.write_bytes(self.certificate)
                response = requests.request(
                    method, f"{self.url}{path}", verify=str(ca_path), **options,
                )
        else:
            response = requests.request(
                method, f"{self.url}{path}", verify=True, **options,
            )
        response.raise_for_status()
        return response

    def health(self) -> dict[str, Any]:
        response = self._request("GET", "/health")
        try:
            return dict(response.json())
        except ValueError:
            return {"status": response.text.strip() or "ok"}

    def create_database(self, *, retention_period: str) -> dict[str, Any]:
        """Create this database with a fixed retention period.

        InfluxDB 3 Core only accepts retention when a database is created; an
        existing database is never silently modified by this helper.
        """
        response = self._request(
            "POST",
            "/api/v3/configure/database",
            json={"db": self.database, "retention_period": retention_period},
        )
        try:
            payload = response.json()
        except ValueError:
            return {"status": response.text.strip() or "created"}
        return dict(payload) if isinstance(payload, dict) else {"data": payload}

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

    def measurements(self, *, max_rows: int = 100) -> list[str]:
        """List bounded user measurements, excluding Influx metadata views."""
        rows = self.query(
            "SELECT table_name, table_schema, table_type "
            "FROM information_schema.tables ORDER BY table_name",
            max_rows=min(max(int(max_rows), 1), 500),
        )
        return [
            str(row["table_name"])
            for row in rows
            if row.get("table_name") is not None
            and str(row.get("table_schema", "iox")).lower() == "iox"
            and str(row.get("table_type", "BASE TABLE")).upper() == "BASE TABLE"
        ]

    def recent_spans(
        self,
        *,
        since_seconds: int = 300,
        limit: int = 100,
        measurement_names: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """Return recent span records from the Collector's ``spans`` table."""
        available = (
            self.measurements(max_rows=500)
            if measurement_names is None
            else measurement_names
        )
        if "spans" not in {name.lower() for name in available}:
            return []
        return self._recent_signal_rows("spans", since_seconds=since_seconds, limit=limit)

    def recent_logs(
        self,
        *,
        since_seconds: int = 300,
        limit: int = 100,
        measurement_names: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """Return recent log records from the Collector's ``logs`` table."""
        available = (
            self.measurements(max_rows=500)
            if measurement_names is None
            else measurement_names
        )
        if "logs" not in {name.lower() for name in available}:
            return []
        return self._recent_signal_rows("logs", since_seconds=since_seconds, limit=limit)

    def recent_metrics(
        self,
        *,
        since_seconds: int = 300,
        limit: int = 100,
        max_tables: int = 12,
        measurement_names: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """Read bounded recent points from metric measurements.

        The Collector's default Influx schema stores each metric name as its
        own measurement. Prioritize MLOX metrics, then sample other tables so
        this convenience view makes a bounded number of queries.
        """
        table_names = [
            name
            for name in (
                measurement_names
                if measurement_names is not None
                else self.measurements(max_rows=500)
            )
            if name.lower() not in {"spans", "logs"}
            and not name.lower().startswith(("system.", "_"))
        ]
        table_names.sort(key=lambda name: (not name.lower().startswith("mlox."), name))
        table_cap = min(max(int(max_tables), 1), MAX_METRIC_TABLES)
        total_cap = min(max(int(limit), 1), MAX_TELEMETRY_ROWS)
        selected = table_names[:table_cap]
        if not selected:
            return []
        per_table = max(1, min(10, total_cap // len(selected)))
        rows: list[dict[str, Any]] = []
        for measurement in selected:
            for row in self._recent_signal_rows(
                measurement,
                since_seconds=since_seconds,
                limit=per_table,
            ):
                rows.append({"measurement": measurement, **row})
        return rows[:total_cap]

    def _recent_signal_rows(
        self, table: str, *, since_seconds: int, limit: int
    ) -> list[dict[str, Any]]:
        window = min(max(int(since_seconds), 1), MAX_TELEMETRY_WINDOW_SECONDS)
        rows = min(max(int(limit), 1), MAX_TELEMETRY_ROWS)
        # Quote table identifiers from information_schema, including any
        # embedded quotes, rather than interpolating them as bare SQL.
        identifier = '"' + str(table).replace('"', '""') + '"'
        try:
            return self.query(
                f"SELECT * FROM {identifier} WHERE time >= now() - INTERVAL "
                f"'{window} seconds' ORDER BY time DESC LIMIT {rows}",
                max_rows=rows,
            )
        except requests.HTTPError as exc:
            # Keep the server response private, but let the TUI identify which
            # signal table InfluxDB rejected.
            exc.influx_table = str(table)
            raise

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
