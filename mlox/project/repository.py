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
from mlox.project.entries import Entry
from mlox.project.operations import (
    OperationsAgent,
    OperationsAgentMessage,
    OperationsAgentProposal,
    OperationsAgentRun,
    OperationsEvent,
)

if TYPE_CHECKING:
    from mlox.config import ServiceConfig

PROJECT_SUFFIX = ".mlox"
PROJECT_FORMAT_VERSION = 1
SCHEMA_VERSION = 5
PLAINTEXT_TEST_ENV = "MLOX_ALLOW_PLAINTEXT_SQLITE"

ENTRIES_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS entries (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    kind TEXT NOT NULL,
    title TEXT NOT NULL,
    body_md TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_entries_project ON entries(project_id);
CREATE INDEX IF NOT EXISTS idx_entries_kind ON entries(project_id, kind);
"""

OPERATIONS_EVENTS_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS operations_events (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    created_at TEXT NOT NULL,
    actor TEXT NOT NULL,
    event_type TEXT NOT NULL,
    target TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'recorded',
    summary TEXT NOT NULL,
    details_json TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_operations_events_project_time
    ON operations_events(project_id, created_at);
"""

OPERATIONS_AGENTS_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS operations_agents (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    role TEXT NOT NULL,
    scope TEXT NOT NULL DEFAULT '',
    description TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'inactive',
    runtime TEXT NOT NULL DEFAULT 'planned',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_operations_agents_project
    ON operations_agents(project_id, created_at);

CREATE TABLE IF NOT EXISTS operations_agent_runs (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    agent_id TEXT NOT NULL,
    pipeline_id TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'queued',
    summary TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_operations_agent_runs_agent
    ON operations_agent_runs(project_id, agent_id, created_at);

CREATE TABLE IF NOT EXISTS operations_agent_messages (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    run_id TEXT NOT NULL REFERENCES operations_agent_runs(id) ON DELETE CASCADE,
    created_at TEXT NOT NULL,
    author TEXT NOT NULL,
    kind TEXT NOT NULL,
    content TEXT NOT NULL,
    details_json TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_operations_agent_messages_run
    ON operations_agent_messages(project_id, run_id, created_at);

CREATE TABLE IF NOT EXISTS operations_agent_proposals (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    agent_id TEXT NOT NULL,
    run_id TEXT NOT NULL REFERENCES operations_agent_runs(id) ON DELETE CASCADE,
    pipeline_id TEXT NOT NULL DEFAULT '',
    headline TEXT NOT NULL,
    description TEXT NOT NULL,
    verification TEXT NOT NULL DEFAULT '',
    actions_json TEXT NOT NULL DEFAULT '[]',
    status TEXT NOT NULL DEFAULT 'open',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_operations_agent_proposals_agent
    ON operations_agent_proposals(project_id, agent_id, created_at);
"""


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
            INSERT INTO schema_info VALUES (1, 5, CURRENT_TIMESTAMP, NULL, NULL);

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
        conn.executescript(ENTRIES_SCHEMA_SQL)
        conn.executescript(OPERATIONS_EVENTS_SCHEMA_SQL)
        conn.executescript(OPERATIONS_AGENTS_SCHEMA_SQL)

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
        if current_version < 3:
            conn.executescript(ENTRIES_SCHEMA_SQL)
        if current_version < 4:
            conn.executescript(OPERATIONS_EVENTS_SCHEMA_SQL)
        if current_version < 5:
            conn.executescript(OPERATIONS_AGENTS_SCHEMA_SQL)
        if current_version < SCHEMA_VERSION:
            conn.execute(
                "UPDATE schema_info SET schema_version=?, applied_at=CURRENT_TIMESTAMP "
                "WHERE singleton=1",
                (SCHEMA_VERSION,),
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

    def save_entry(self, entry: Entry) -> Entry:
        """Insert a new entry or update an existing one; returns the entry."""
        now = utcnow()
        with self.connection() as conn:
            pid = self.project_id(conn)
            if entry.id:
                conn.execute(
                    "UPDATE entries SET kind=?, title=?, body_md=?, updated_at=? "
                    "WHERE id=? AND project_id=?",
                    (entry.kind, entry.title, entry.body_md, now, entry.id, pid),
                )
            else:
                entry.id = str(uuid4())
                conn.execute(
                    "INSERT INTO entries "
                    "(id, project_id, kind, title, body_md, created_at, updated_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (entry.id, pid, entry.kind, entry.title, entry.body_md, now, now),
                )
                entry.created_at = now
            entry.updated_at = now
        return entry

    def get_entry(self, entry_id: str) -> Entry | None:
        with self.connection() as conn:
            pid = self.project_id(conn)
            row = conn.execute(
                "SELECT id, kind, title, body_md, created_at, updated_at FROM entries "
                "WHERE id=? AND project_id=?",
                (entry_id, pid),
            ).fetchone()
        if row is None:
            return None
        return Entry(
            id=row[0], kind=row[1], title=row[2], body_md=row[3],
            created_at=row[4], updated_at=row[5],
        )

    def list_entries(self, kind: str | None = None) -> list[Entry]:
        with self.connection() as conn:
            pid = self.project_id(conn)
            if kind is None:
                rows = conn.execute(
                    "SELECT id, kind, title, body_md, created_at, updated_at FROM entries "
                    "WHERE project_id=? ORDER BY created_at, id",
                    (pid,),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT id, kind, title, body_md, created_at, updated_at FROM entries "
                    "WHERE project_id=? AND kind=? ORDER BY created_at, id",
                    (pid, kind),
                ).fetchall()
        return [
            Entry(
                id=row[0], kind=row[1], title=row[2], body_md=row[3],
                created_at=row[4], updated_at=row[5],
            )
            for row in rows
        ]

    def find_entry_by_title(self, title: str, kind: str | None = None) -> Entry | None:
        """First entry whose title matches (exact, then case-insensitive)."""
        entries = self.list_entries(kind)
        wanted = title.strip().casefold()
        for entry in entries:
            if entry.title == title:
                return entry
        for entry in entries:
            if entry.title.strip().casefold() == wanted:
                return entry
        return None

    def delete_entry(self, entry_id: str) -> None:
        with self.connection() as conn:
            pid = self.project_id(conn)
            conn.execute(
                "DELETE FROM entries WHERE id=? AND project_id=?", (entry_id, pid)
            )

    def record_operations_event(self, event: OperationsEvent) -> OperationsEvent:
        """Append an immutable event to the operations audit trail."""

        event_id = event.id or str(uuid4())
        created_at = event.created_at or utcnow()
        with self.connection() as conn:
            conn.execute(
                "INSERT INTO operations_events "
                "(id, project_id, created_at, actor, event_type, target, status, "
                "summary, details_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    event_id,
                    self.project_id(conn),
                    created_at,
                    event.actor,
                    event.event_type,
                    event.target,
                    event.status,
                    event.summary,
                    json.dumps(event.details),
                ),
            )
        return OperationsEvent(
            id=event_id,
            created_at=created_at,
            actor=event.actor,
            event_type=event.event_type,
            target=event.target,
            status=event.status,
            summary=event.summary,
            details=dict(event.details),
        )

    def list_operations_events(self, limit: int = 200) -> list[OperationsEvent]:
        """Return newest operations events first, bounded by ``limit``."""

        bounded_limit = max(1, min(int(limit), 1000))
        with self.connection() as conn:
            rows = conn.execute(
                "SELECT id, created_at, actor, event_type, target, status, summary, "
                "details_json FROM operations_events WHERE project_id=? "
                "ORDER BY created_at DESC, id DESC LIMIT ?",
                (self.project_id(conn), bounded_limit),
            ).fetchall()
        return [
            OperationsEvent(
                id=row[0],
                created_at=row[1],
                actor=row[2],
                event_type=row[3],
                target=row[4],
                status=row[5],
                summary=row[6],
                details=json.loads(row[7]),
            )
            for row in rows
        ]

    def save_operations_agent(self, agent: OperationsAgent) -> OperationsAgent:
        """Create or update a durable Operations team profile."""

        now = utcnow()
        agent_id = agent.id or str(uuid4())
        created_at = agent.created_at or now
        with self.connection() as conn:
            pid = self.project_id(conn)
            conn.execute(
                "INSERT INTO operations_agents "
                "(id, project_id, name, role, scope, description, status, runtime, "
                "created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(id) DO UPDATE SET name=excluded.name, role=excluded.role, "
                "scope=excluded.scope, description=excluded.description, "
                "status=excluded.status, runtime=excluded.runtime, updated_at=excluded.updated_at",
                (
                    agent_id, pid, agent.name, agent.role, agent.scope,
                    agent.description, agent.status, agent.runtime, created_at, now,
                ),
            )
        return OperationsAgent(
            id=agent_id, name=agent.name, role=agent.role, scope=agent.scope,
            description=agent.description, status=agent.status, runtime=agent.runtime,
            created_at=created_at, updated_at=now,
        )

    def list_operations_agents(self) -> list[OperationsAgent]:
        with self.connection() as conn:
            rows = conn.execute(
                "SELECT id, name, role, scope, description, status, runtime, created_at, "
                "updated_at FROM operations_agents WHERE project_id=? "
                "ORDER BY created_at, id",
                (self.project_id(conn),),
            ).fetchall()
        return [
            OperationsAgent(
                id=row[0], name=row[1], role=row[2], scope=row[3], description=row[4],
                status=row[5], runtime=row[6], created_at=row[7], updated_at=row[8],
            )
            for row in rows
        ]

    def archive_operations_agent(self, agent_id: str) -> bool:
        with self.connection() as conn:
            cursor = conn.execute(
                "UPDATE operations_agents SET status='archived', updated_at=? "
                "WHERE id=? AND project_id=?",
                (utcnow(), agent_id, self.project_id(conn)),
            )
        return bool(cursor.rowcount)

    def save_operations_agent_run(self, run: OperationsAgentRun) -> OperationsAgentRun:
        """Create or update a durable Operations agent work item."""

        now = utcnow()
        run_id = run.id or str(uuid4())
        created_at = run.created_at or now
        with self.connection() as conn:
            conn.execute(
                "INSERT INTO operations_agent_runs "
                "(id, project_id, agent_id, pipeline_id, status, summary, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?) ON CONFLICT(id) DO UPDATE SET "
                "agent_id=excluded.agent_id, pipeline_id=excluded.pipeline_id, "
                "status=excluded.status, summary=excluded.summary, updated_at=excluded.updated_at",
                (
                    run_id, self.project_id(conn), run.agent_id, run.pipeline_id,
                    run.status, run.summary, created_at, now,
                ),
            )
        return OperationsAgentRun(
            id=run_id, agent_id=run.agent_id, pipeline_id=run.pipeline_id,
            status=run.status, summary=run.summary, created_at=created_at, updated_at=now,
        )

    def list_operations_agent_runs(
        self, agent_id: str, limit: int = 50
    ) -> list[OperationsAgentRun]:
        bounded_limit = max(1, min(int(limit), 500))
        with self.connection() as conn:
            rows = conn.execute(
                "SELECT id, agent_id, pipeline_id, status, summary, created_at, updated_at "
                "FROM operations_agent_runs WHERE project_id=? AND agent_id=? "
                "ORDER BY created_at DESC, id DESC LIMIT ?",
                (self.project_id(conn), agent_id, bounded_limit),
            ).fetchall()
        return [
            OperationsAgentRun(
                id=row[0], agent_id=row[1], pipeline_id=row[2], status=row[3],
                summary=row[4], created_at=row[5], updated_at=row[6],
            )
            for row in rows
        ]

    def record_operations_agent_message(
        self, message: OperationsAgentMessage
    ) -> OperationsAgentMessage:
        message_id = message.id or str(uuid4())
        created_at = message.created_at or utcnow()
        with self.connection() as conn:
            conn.execute(
                "INSERT INTO operations_agent_messages "
                "(id, project_id, run_id, created_at, author, kind, content, details_json) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    message_id, self.project_id(conn), message.run_id, created_at,
                    message.author, message.kind, message.content, json.dumps(message.details),
                ),
            )
        return OperationsAgentMessage(
            id=message_id, run_id=message.run_id, author=message.author,
            kind=message.kind, content=message.content, details=dict(message.details),
            created_at=created_at,
        )

    def list_operations_agent_messages(
        self, agent_id: str, limit: int = 100
    ) -> list[OperationsAgentMessage]:
        bounded_limit = max(1, min(int(limit), 500))
        with self.connection() as conn:
            rows = conn.execute(
                "SELECT m.id, m.run_id, m.created_at, m.author, m.kind, m.content, "
                "m.details_json FROM operations_agent_messages m "
                "JOIN operations_agent_runs r ON r.id=m.run_id "
                "WHERE m.project_id=? AND r.agent_id=? "
                "ORDER BY m.created_at DESC, m.id DESC LIMIT ?",
                (self.project_id(conn), agent_id, bounded_limit),
            ).fetchall()
        return [
            OperationsAgentMessage(
                id=row[0], run_id=row[1], created_at=row[2], author=row[3],
                kind=row[4], content=row[5], details=json.loads(row[6]),
            )
            for row in rows
        ]

    def save_operations_agent_proposal(
        self, proposal: OperationsAgentProposal
    ) -> OperationsAgentProposal:
        now = utcnow()
        proposal_id = proposal.id or str(uuid4())
        created_at = proposal.created_at or now
        with self.connection() as conn:
            conn.execute(
                "INSERT INTO operations_agent_proposals "
                "(id, project_id, agent_id, run_id, pipeline_id, headline, description, "
                "verification, actions_json, status, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) ON CONFLICT(id) DO UPDATE SET "
                "headline=excluded.headline, description=excluded.description, "
                "verification=excluded.verification, actions_json=excluded.actions_json, "
                "status=excluded.status, updated_at=excluded.updated_at",
                (
                    proposal_id, self.project_id(conn), proposal.agent_id, proposal.run_id,
                    proposal.pipeline_id, proposal.headline, proposal.description,
                    proposal.verification, json.dumps(proposal.actions), proposal.status,
                    created_at, now,
                ),
            )
        return OperationsAgentProposal(
            id=proposal_id, agent_id=proposal.agent_id, run_id=proposal.run_id,
            pipeline_id=proposal.pipeline_id, headline=proposal.headline,
            description=proposal.description, verification=proposal.verification,
            actions=list(proposal.actions), status=proposal.status,
            created_at=created_at, updated_at=now,
        )

    def list_operations_agent_proposals(
        self, agent_id: str, limit: int = 50
    ) -> list[OperationsAgentProposal]:
        bounded_limit = max(1, min(int(limit), 500))
        with self.connection() as conn:
            rows = conn.execute(
                "SELECT id, agent_id, run_id, pipeline_id, headline, description, "
                "verification, actions_json, status, created_at, updated_at "
                "FROM operations_agent_proposals WHERE project_id=? AND agent_id=? "
                "ORDER BY created_at DESC, id DESC LIMIT ?",
                (self.project_id(conn), agent_id, bounded_limit),
            ).fetchall()
        return [
            OperationsAgentProposal(
                id=row[0], agent_id=row[1], run_id=row[2], pipeline_id=row[3],
                headline=row[4], description=row[5], verification=row[6],
                actions=json.loads(row[7]), status=row[8], created_at=row[9], updated_at=row[10],
            )
            for row in rows
        ]

    def record_legacy_import(self, source_path: str, source_sha256: str, resources: int, secrets: int) -> None:
        with self.connection() as conn:
            conn.execute(
                "INSERT INTO legacy_imports VALUES(?,?,?,?,?,?,?)",
                (str(uuid4()), self.project_id(conn), source_path, source_sha256, utcnow(), resources, secrets),
            )

    def integrity_check(self) -> bool:
        with self.connection() as conn:
            return conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
