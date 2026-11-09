"""Embedded DuckDB client for a PostgreSQL/S3 DuckLake."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence
from urllib.parse import urlsplit

from mlox.secret_manager import AbstractSecretManager


def _identifier(value: str) -> str:
    if not value or "\x00" in value:
        raise ValueError("SQL identifier must not be empty or contain NUL")
    return '"' + value.replace('"', '""') + '"'


def _literal(value: str) -> str:
    if "\x00" in value:
        raise ValueError("SQL value must not contain NUL")
    return "'" + value.replace("'", "''") + "'"


def _required(secret: Mapping[str, Any], *names: str) -> Any:
    for name in names:
        value = secret.get(name)
        if value is not None and value != "":
            return value
    raise ValueError(f"Secret is missing required field: {names[0]}")


@dataclass
class DuckLakeClient:
    """Create isolated connections; credentials are loaded on each connection."""

    secret_manager: AbstractSecretManager = field(repr=False)
    postgres_secret_name: str
    s3_secret_name: str
    data_path: str
    metadata_schema: str = "ducklake"
    catalog_name: str = "lake"
    postgres_defaults: Mapping[str, Any] = field(default_factory=dict)
    s3_defaults: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.data_path.startswith("s3://") or not self.data_path[5:].split("/")[0]:
            raise ValueError("data_path must be an s3://bucket/prefix/ URL")
        self.data_path = self.data_path.rstrip("/") + "/"
        _identifier(self.catalog_name)
        _identifier(self.metadata_schema)

    def _secret(self, name: str, *nested_keys: str) -> Mapping[str, Any]:
        value = self.secret_manager.load_secret(name)
        if not isinstance(value, Mapping):
            raise ValueError(f"Secret {name!r} must exist and contain a mapping")
        for nested_key in nested_keys:
            if nested_key in value:
                nested = value[nested_key]
                if not isinstance(nested, Mapping):
                    raise ValueError(f"Secret {name!r} field {nested_key!r} must contain a mapping")
                return nested
        return value

    def connect(self, *, create: bool = False, read_only: bool = False):
        """Open an in-memory DuckDB connection; creation requires explicit opt-in."""
        if create and read_only:
            raise ValueError("Cannot create a lake in read-only mode")
        try:
            import duckdb
        except ImportError as exc:
            raise ImportError("Install the DuckLake client extra: pip install 'busysloths-mlox[ducklake]'") from exc
        pg = {**self.postgres_defaults, **self._secret(self.postgres_secret_name, "postgres_connection")}
        s3 = {**self.s3_defaults, **self._secret(self.s3_secret_name, "s3_connection", "minio_root_credentials")}
        endpoint = str(_required(s3, "endpoint"))
        parsed = urlsplit(endpoint if "://" in endpoint else "https://" + endpoint)
        if parsed.scheme not in ("http", "https") or not parsed.netloc or parsed.path not in ("", "/") or parsed.query or parsed.fragment or parsed.username:
            raise ValueError("S3 endpoint must be an HTTP(S) host and optional port")
        url_style = str(s3.get("url_style", "path"))
        if url_style not in ("path", "vhost"):
            raise ValueError("S3 url_style must be 'path' or 'vhost'")
        conn = duckdb.connect(":memory:")
        try:
            for extension in ("ducklake", "postgres", "httpfs"):
                conn.execute(f"INSTALL {extension}")
                conn.execute(f"LOAD {extension}")
            pg_options = "TYPE postgres, HOST ?, PORT ?, DATABASE ?, USER ?, PASSWORD ?"
            pg_params = [str(_required(pg, "host")), int(pg.get("port", 5432)), str(_required(pg, "database", "dbname")), str(_required(pg, "username", "user")), str(_required(pg, "password"))]
            for key in ("sslmode", "sslrootcert"):
                if pg.get(key):
                    pg_options += f", {key.upper()} ?"
                    pg_params.append(str(pg[key]))
            conn.execute(f"CREATE SECRET mlox_pg ({pg_options})", pg_params)
            if s3.get("ca_cert_file"):
                conn.execute("SET ca_cert_file = ?", [str(s3["ca_cert_file"])])
            s3_options = "TYPE s3, KEY_ID ?, SECRET ?, ENDPOINT ?, REGION ?, URL_STYLE ?, USE_SSL ?"
            params = [str(_required(s3, "access_key", "access_key_id", "username")), str(_required(s3, "secret_key", "secret_access_key", "password")), parsed.netloc, str(s3.get("region", "us-east-1")), url_style, parsed.scheme == "https"]
            if s3.get("session_token"):
                s3_options += ", SESSION_TOKEN ?"
                params.append(str(s3["session_token"]))
            conn.execute(f"CREATE SECRET mlox_s3 ({s3_options})", params)
            options = ["META_SECRET 'mlox_pg'", f"METADATA_SCHEMA {_literal(self.metadata_schema)}", f"CREATE_IF_NOT_EXISTS {'true' if create else 'false'}"]
            if create:
                options.append(f"DATA_PATH {_literal(self.data_path)}")
            if read_only:
                options.append("READ_ONLY")
            conn.execute(f"ATTACH 'ducklake:postgres:' AS {_identifier(self.catalog_name)} ({', '.join(options)})")
            # Ensure a pre-existing catalog is the one the user intended to attach.
            actual_path = conn.execute("SELECT data_path FROM ducklake_settings(?)", [self.catalog_name]).fetchone()[0]
            if actual_path.rstrip("/") + "/" != self.data_path:
                raise ValueError("Existing DuckLake data path does not match configured data path")
            conn.execute(f"USE {_identifier(self.catalog_name)}")
            return conn
        except BaseException:
            conn.close()
            raise

    def create_lake(self) -> None:
        with self.connect(create=True) as conn:
            pass

    def query(self, sql: str, parameters: Sequence[Any] | None = None) -> list[tuple]:
        with self.connect() as conn:
            return conn.execute(sql, parameters or []).fetchall()

    def read_dataframe(self, sql: str, parameters: Sequence[Any] | None = None):
        """Run a query and return a pandas DataFrame (requires pandas)."""
        with self.connect() as conn:
            return conn.execute(sql, parameters or []).fetchdf()

    def list_schemas(self) -> list[str]:
        return [row[0] for row in self.query("SELECT schema_name FROM information_schema.schemata WHERE catalog_name = ? ORDER BY schema_name", [self.catalog_name])]

    def list_tables(self, schema: str = "main") -> list[str]:
        return [row[0] for row in self.query("SELECT table_name FROM information_schema.tables WHERE table_catalog = ? AND table_schema = ? ORDER BY table_name", [self.catalog_name, schema])]

    def write_dataframe(self, table: str, dataframe: Any, *, schema: str = "main", mode: str = "append") -> None:
        if mode not in ("append", "create", "replace"):
            raise ValueError("mode must be append, create or replace")
        target = ".".join(_identifier(part) for part in (self.catalog_name, schema, table))
        with self.connect() as conn:
            conn.register("_mlox_input", dataframe)
            if mode == "append":
                conn.execute(f"INSERT INTO {target} SELECT * FROM _mlox_input")
            else:
                verb = "CREATE OR REPLACE TABLE" if mode == "replace" else "CREATE TABLE"
                conn.execute(f"{verb} {target} AS SELECT * FROM _mlox_input")

    def check(self) -> dict[str, str]:
        """Check catalog access without creating it or altering its data."""
        with self.connect(read_only=True) as conn:
            conn.execute(f"SELECT * FROM {_identifier(self.catalog_name)}.settings()").fetchone()
            conn.execute("SELECT count(*) FROM glob(?)", [self.data_path + "*"]).fetchone()
        return {"status": "running"}
