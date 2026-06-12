"""Encrypted, single-file project persistence for MLOX.

The schema deliberately uses portable SQL types and application-generated UUIDs so a
future PostgreSQL repository can implement the same contract without changing domain
objects. SQLCipher is mandatory in production; stdlib sqlite is allowed only when the
explicit test escape hatch is set.
"""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, Iterable, Iterator
from uuid import uuid4

from mlox.infra import Infrastructure

if TYPE_CHECKING:
    from mlox.config import ServiceConfig

PROJECT_SUFFIX = ".mlox"
PROJECT_FORMAT_VERSION = 1
SCHEMA_VERSION = 2
PLAINTEXT_TEST_ENV = "MLOX_ALLOW_PLAINTEXT_SQLITE"


class ProjectStorageError(RuntimeError):
    """Base error for project storage failures."""


class ProjectAlreadyExistsError(ProjectStorageError):
    """Raised when creating over an existing project."""


class ProjectNotFoundError(ProjectStorageError):
    """Raised when a project file does not exist."""


class InvalidProjectPasswordError(ProjectStorageError):
    """Raised when a project cannot be decrypted or validated."""


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def resolve_project_path(project: str | Path) -> Path:
    path = Path(project).expanduser()
    if path.suffix != PROJECT_SUFFIX:
        path = path.with_suffix(PROJECT_SUFFIX)
    if not path.is_absolute():
        root = Path(os.environ.get("MLOX_PROJECT_DIR", ".")).expanduser()
        path = root / path
    return path.resolve()


def _connect(path: Path):
    if os.environ.get(PLAINTEXT_TEST_ENV) == "1":
        return sqlite3.connect(str(path))

    try:
        from sqlcipher3 import dbapi2 as sqlcipher

        return sqlcipher.connect(str(path))
    except ImportError as exc:
        raise ProjectStorageError(
            "SQLCipher support is unavailable. Install the sqlcipher3 package."
        ) from exc


def _quote_pragma(value: str) -> str:
    return value.replace("'", "''")


def _password_check(password: str, salt_hex: str) -> str:
    salt = bytes.fromhex(salt_hex)
    return hashlib.scrypt(
        password.encode("utf-8"), salt=salt, n=2**14, r=8, p=1
    ).hex()


class SqlCipherRepository:
    """Repository for one encrypted MLOX project file."""

    def __init__(
        self,
        path: str | Path,
        password: str,
        connector: Callable[[Path], Any] = _connect,
        config_catalog: Callable[[], Iterable[ServiceConfig]] | None = None,
    ) -> None:
        if not password:
            raise ValueError("A non-empty project password is required.")
        self.path = resolve_project_path(path)
        self.password = password
        self._connector = connector
        self._config_catalog = config_catalog

    @classmethod
    def create(cls, path: str | Path, password: str, name: str | None = None):
        repository = cls(path, password)
        if repository.path.exists():
            raise ProjectAlreadyExistsError(
                f"Project already exists: {repository.path}"
            )
        repository.path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with repository.connection() as conn:
                repository._create_schema(conn)
                salt = os.urandom(16).hex()
                conn.execute(
                    "UPDATE schema_info SET key_salt=?, key_check=? WHERE singleton=1",
                    (salt, _password_check(password, salt)),
                )
                project_id = str(uuid4())
                data_source_id = str(uuid4())
                now = utcnow()
                project_name = name or repository.path.stem
                conn.execute(
                    "INSERT INTO projects "
                    "(id, name, description, format_version, application_version, created_at, "
                    "last_opened_at, active_data_source_id) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        project_id, project_name, "", PROJECT_FORMAT_VERSION, "0.1.0",
                        now, now, data_source_id,
                    ),
                )
                conn.execute(
                    "INSERT INTO data_sources "
                    "(id, project_id, kind, location, config_json, created_at) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (data_source_id, project_id, "sqlcipher", "self", "{}", now),
                )
            return repository.open()
        except Exception:
            repository.discard()
            raise

    def open(self):
        if not self.path.exists():
            raise ProjectNotFoundError(f"Project does not exist: {self.path}")
        try:
            with self.connection() as conn:
                row = conn.execute(
                    "SELECT schema_version, key_salt, key_check FROM schema_info WHERE singleton = 1"
                ).fetchone()
                if row is None or int(row[0]) > SCHEMA_VERSION:
                    raise ProjectStorageError("Unsupported project schema version.")
                if row[1] is not None and _password_check(self.password, row[1]) != row[2]:
                    raise InvalidProjectPasswordError("Invalid project password.")
                self._upgrade_schema(conn, int(row[0]))
                conn.execute(
                    "UPDATE projects SET last_opened_at = ?", (utcnow(),)
                )
        except ProjectStorageError:
            raise
        except Exception as exc:
            raise InvalidProjectPasswordError(
                f"Could not decrypt or validate project: {self.path}"
            ) from exc
        return self

    @contextmanager
    def connection(self) -> Iterator[Any]:
        conn = self._connector(self.path)
        try:
            conn.execute(f"PRAGMA key = '{_quote_pragma(self.password)}'")
            if os.environ.get(PLAINTEXT_TEST_ENV) != "1":
                cipher = conn.execute("PRAGMA cipher_version").fetchone()
                if not cipher or not cipher[0]:
                    raise ProjectStorageError("The database driver is not SQLCipher-enabled.")
            conn.execute("PRAGMA foreign_keys = ON")
            conn.execute("PRAGMA busy_timeout = 5000")
            conn.execute("PRAGMA journal_mode = DELETE")
            conn.execute("PRAGMA synchronous = FULL")
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def discard(self) -> None:
        for candidate in (self.path, Path(f"{self.path}-wal"), Path(f"{self.path}-shm")):
            candidate.unlink(missing_ok=True)

    def _create_schema(self, conn: Any) -> None:
        conn.executescript(
            """
            CREATE TABLE schema_info (
                singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
                schema_version INTEGER NOT NULL,
                applied_at TEXT NOT NULL,
                key_salt TEXT,
                key_check TEXT
            );
            INSERT INTO schema_info VALUES (1, 2, CURRENT_TIMESTAMP, NULL, NULL);

            CREATE TABLE projects (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                format_version INTEGER NOT NULL,
                application_version TEXT NOT NULL,
                created_at TEXT NOT NULL,
                last_opened_at TEXT NOT NULL,
                active_data_source_id TEXT NOT NULL,
                active_secret_manager_kind TEXT NOT NULL DEFAULT 'embedded',
                active_secret_manager_service_uuid TEXT
            );
            CREATE TABLE data_sources (
                id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                kind TEXT NOT NULL,
                location TEXT NOT NULL,
                config_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL,
                UNIQUE(project_id, id)
            );
            CREATE TABLE infrastructure_snapshots (
                project_id TEXT PRIMARY KEY REFERENCES projects(id) ON DELETE CASCADE,
                payload_json TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE bundles (
                id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                name TEXT NOT NULL,
                payload_json TEXT NOT NULL
            );
            CREATE TABLE servers (
                id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                bundle_id TEXT NOT NULL REFERENCES bundles(id) ON DELETE CASCADE,
                name TEXT,
                address TEXT,
                payload_json TEXT NOT NULL
            );
            CREATE TABLE services (
                id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                bundle_id TEXT NOT NULL REFERENCES bundles(id) ON DELETE CASCADE,
                name TEXT,
                service_type TEXT,
                payload_json TEXT NOT NULL
            );
            CREATE TABLE secrets (
                project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                name TEXT NOT NULL,
                value_json TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                PRIMARY KEY(project_id, name)
            );
            CREATE TABLE legacy_imports (
                id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                source_path TEXT NOT NULL,
                source_sha256 TEXT NOT NULL,
                imported_at TEXT NOT NULL,
                resource_count INTEGER NOT NULL,
                secret_count INTEGER NOT NULL
            );
            CREATE INDEX idx_servers_project ON servers(project_id);
            CREATE INDEX idx_services_project ON services(project_id);
            CREATE INDEX idx_services_bundle ON services(bundle_id);
            """
        )

    @staticmethod
    def _upgrade_schema(conn: Any, current_version: int) -> None:
        if current_version < 2:
            conn.execute(
                "ALTER TABLE projects ADD COLUMN "
                "active_secret_manager_kind TEXT NOT NULL DEFAULT 'embedded'"
            )
            conn.execute(
                "ALTER TABLE projects ADD COLUMN active_secret_manager_service_uuid TEXT"
            )
            conn.execute(
                "UPDATE schema_info SET schema_version=2, applied_at=CURRENT_TIMESTAMP "
                "WHERE singleton=1"
            )

    def project_id(self, conn: Any | None = None) -> str:
        if conn is not None:
            return str(conn.execute("SELECT id FROM projects LIMIT 1").fetchone()[0])
        with self.connection() as owned:
            return self.project_id(owned)

    def load(self):
        """Load the complete workspace state."""
        from mlox.project.state import WorkspaceState

        with self.connection() as conn:
            row = conn.execute(
                "SELECT p.id, p.name, p.description, p.application_version, p.created_at, "
                "p.last_opened_at, d.id, d.kind, d.location, d.config_json, "
                "p.active_secret_manager_kind, p.active_secret_manager_service_uuid "
                "FROM projects p JOIN data_sources d ON d.id = p.active_data_source_id"
            ).fetchone()
            infra_row = conn.execute(
                "SELECT payload_json FROM infrastructure_snapshots WHERE project_id=?",
                (row[0],),
            ).fetchone()
        infrastructure = (
            Infrastructure()
            if infra_row is None
            else Infrastructure.from_dict(
                json.loads(infra_row[0]),
                configs=(
                    self._config_catalog()
                    if self._config_catalog is not None
                    else None
                ),
            )
        )
        return WorkspaceState(
            id=row[0],
            name=row[1],
            descr=row[2],
            version=str(row[3]),
            created_at=row[4],
            last_opened_at=row[5],
            data_source_id=row[6],
            data_source_kind=row[7],
            data_source_location=row[8],
            data_source_config=json.loads(row[9]),
            secret_manager_kind=row[10],
            secret_manager_service_uuid=row[11],
            infrastructure=infrastructure,
        )

    def save(self, project: Any) -> None:
        """Persist project metadata and infrastructure atomically."""
        payload = project.infrastructure.to_dict()
        with self.connection() as conn:
            self._save_project(conn, project)
            self._save_infrastructure(conn, project.id, payload)

    @staticmethod
    def _save_project(conn: Any, project: Any) -> None:
        conn.execute(
            "UPDATE projects SET name=?, description=?, application_version=?, "
            "created_at=?, last_opened_at=?, active_secret_manager_kind=?, "
            "active_secret_manager_service_uuid=? WHERE id=?",
            (
                project.name,
                project.descr,
                project.version,
                project.created_at,
                project.last_opened_at,
                project.secret_manager_kind,
                project.secret_manager_service_uuid,
                project.id,
            ),
        )

    @staticmethod
    def _save_infrastructure(
        conn: Any,
        project_id: str,
        payload: dict[str, Any],
    ) -> None:
        now = utcnow()
        conn.execute(
            "INSERT INTO infrastructure_snapshots(project_id,payload_json,updated_at) "
            "VALUES(?,?,?) ON CONFLICT(project_id) DO UPDATE SET "
            "payload_json=excluded.payload_json, updated_at=excluded.updated_at",
            (project_id, json.dumps(payload), now),
        )
        conn.execute("DELETE FROM services WHERE project_id=?", (project_id,))
        conn.execute("DELETE FROM servers WHERE project_id=?", (project_id,))
        conn.execute("DELETE FROM bundles WHERE project_id=?", (project_id,))
        for bundle in payload.get("bundles", []):
            bundle_id = str(uuid4())
            conn.execute(
                "INSERT INTO bundles VALUES(?,?,?,?)",
                (
                    bundle_id,
                    project_id,
                    bundle.get("name", ""),
                    json.dumps(bundle),
                ),
            )
            server = bundle.get("server", {})
            server_id = str(server.get("uuid") or uuid4())
            conn.execute(
                "INSERT INTO servers VALUES(?,?,?,?,?,?)",
                (
                    server_id,
                    project_id,
                    bundle_id,
                    server.get("name"),
                    server.get("ip"),
                    json.dumps(server),
                ),
            )
            for service in bundle.get("services", []):
                service_id = str(service.get("uuid") or uuid4())
                conn.execute(
                    "INSERT INTO services VALUES(?,?,?,?,?,?)",
                    (
                        service_id,
                        project_id,
                        bundle_id,
                        service.get("name"),
                        service.get("_type") or service.get("type"),
                        json.dumps(service),
                    ),
                )

    def save_secret(self, name: str, value: Any) -> None:
        with self.connection() as conn:
            pid = self.project_id(conn)
            conn.execute(
                "INSERT INTO secrets(project_id,name,value_json,updated_at) VALUES(?,?,?,?) "
                "ON CONFLICT(project_id,name) DO UPDATE SET value_json=excluded.value_json, "
                "updated_at=excluded.updated_at",
                (pid, name, json.dumps(value), utcnow()),
            )

    def load_secret(self, name: str) -> Any | None:
        with self.connection() as conn:
            pid = self.project_id(conn)
            row = conn.execute(
                "SELECT value_json FROM secrets WHERE project_id=? AND name=?", (pid, name)
            ).fetchone()
        return None if row is None else json.loads(row[0])

    def list_secrets(self, keys_only: bool = False) -> dict[str, Any]:
        with self.connection() as conn:
            pid = self.project_id(conn)
            rows = conn.execute(
                "SELECT name,value_json FROM secrets WHERE project_id=? ORDER BY name", (pid,)
            ).fetchall()
        return {row[0]: None if keys_only else json.loads(row[1]) for row in rows}

    def record_legacy_import(self, source_path: str, source_sha256: str, resources: int, secrets: int) -> None:
        with self.connection() as conn:
            conn.execute(
                "INSERT INTO legacy_imports VALUES(?,?,?,?,?,?,?)",
                (str(uuid4()), self.project_id(conn), source_path, source_sha256, utcnow(), resources, secrets),
            )

    def integrity_check(self) -> bool:
        with self.connection() as conn:
            return conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
