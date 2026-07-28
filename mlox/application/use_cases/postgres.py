"""Read-only PostgreSQL catalog and table browsing use cases."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import date, datetime, time
from decimal import Decimal
import os
import tempfile
from typing import Any, Iterator

from mlox.application.result import OperationResult


DEFAULT_PAGE_SIZE = 50
MAX_CELL_LENGTH = 500


def _load_driver():
    try:
        import psycopg2
        from psycopg2 import sql
    except ImportError as exc:  # pragma: no cover - depends on optional runtime extra
        raise RuntimeError(
            "Postgres browsing requires psycopg2-binary. Install mlox with the TUI extra."
        ) from exc
    return psycopg2, sql


@contextmanager
def _certificate_file(certificate: str | None) -> Iterator[str | None]:
    if not certificate:
        yield None
        return

    path: str | None = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".pem", delete=False) as cert:
            cert.write(certificate)
            path = cert.name
        yield path
    finally:
        if path and os.path.exists(path):
            os.remove(path)


def _connection_kwargs(
    service: Any,
    database: str,
    certificate_path: str | None,
) -> dict[str, Any]:
    urls = getattr(service, "service_urls", {}) or {}
    host = urls.get("Postgres IP") or urls.get("host")
    kwargs: dict[str, Any] = {
        "host": host,
        "port": int(getattr(service, "port", 5432)),
        "dbname": database,
        "user": getattr(service, "user", ""),
        "password": getattr(service, "pw", ""),
        "connect_timeout": 5,
        "sslmode": "verify-full" if certificate_path else "require",
    }
    if certificate_path:
        kwargs["sslrootcert"] = certificate_path
    return kwargs


def load_postgres_catalog(service: Any) -> OperationResult:
    """Return databases, schemas, tables, and lightweight activity statistics."""

    try:
        psycopg2, _ = _load_driver()
        databases: list[dict[str, Any]] = []
        tables: list[dict[str, Any]] = []
        errors: list[dict[str, str]] = []
        with _certificate_file(getattr(service, "certificate", None)) as cert_path:
            with psycopg2.connect(
                **_connection_kwargs(service, getattr(service, "db", "postgres"), cert_path)
            ) as connection:
                with connection.cursor() as cursor:
                    cursor.execute(
                        """
                        SELECT datname, pg_get_userbyid(datdba), pg_database_size(datname)
                        FROM pg_database
                        WHERE NOT datistemplate AND datallowconn
                        ORDER BY datname
                        """
                    )
                    databases = [
                        {"name": name, "owner": owner, "size_bytes": int(size or 0)}
                        for name, owner, size in cursor.fetchall()
                    ]

            for database in databases:
                name = database["name"]
                try:
                    with psycopg2.connect(
                        **_connection_kwargs(service, name, cert_path)
                    ) as connection:
                        with connection.cursor() as cursor:
                            cursor.execute(
                                """
                                SELECT n.nspname, c.relname,
                                       CASE c.relkind WHEN 'v' THEN 'view'
                                            WHEN 'm' THEN 'materialized view'
                                            ELSE 'table' END,
                                       GREATEST(c.reltuples, 0)::bigint,
                                       pg_total_relation_size(c.oid),
                                       COALESCE(s.n_tup_ins, 0), COALESCE(s.n_tup_upd, 0),
                                       COALESCE(s.n_tup_del, 0),
                                       GREATEST(s.last_vacuum, s.last_autovacuum,
                                                s.last_analyze, s.last_autoanalyze)
                                FROM pg_class c
                                JOIN pg_namespace n ON n.oid = c.relnamespace
                                LEFT JOIN pg_stat_user_tables s ON s.relid = c.oid
                                WHERE c.relkind IN ('r', 'p', 'v', 'm')
                                  AND n.nspname NOT IN ('pg_catalog', 'information_schema')
                                  AND n.nspname !~ '^pg_toast'
                                ORDER BY n.nspname, c.relname
                                """
                            )
                            for row in cursor.fetchall():
                                tables.append(
                                    {
                                        "database": name,
                                        "schema": row[0],
                                        "name": row[1],
                                        "kind": row[2],
                                        "estimated_rows": int(row[3] or 0),
                                        "size_bytes": int(row[4] or 0),
                                        "inserts": int(row[5] or 0),
                                        "updates": int(row[6] or 0),
                                        "deletes": int(row[7] or 0),
                                        "last_maintenance": row[8],
                                    }
                                )
                except Exception as exc:
                    errors.append({"database": name, "error": str(exc).strip()})
    except Exception as exc:
        return OperationResult(False, 1, f"Could not inspect Postgres: {exc}")

    return OperationResult(
        True,
        0,
        "Postgres catalog loaded.",
        {"databases": databases, "tables": tables, "errors": errors},
    )


def load_postgres_table_page(
    service: Any,
    *,
    database: str,
    schema: str,
    table: str,
    page: int = 0,
    page_size: int = DEFAULT_PAGE_SIZE,
) -> OperationResult:
    """Return one safely quoted, read-only page from a table or view."""

    page = max(0, int(page))
    page_size = max(1, min(int(page_size), 200))
    try:
        psycopg2, sql = _load_driver()
        with _certificate_file(getattr(service, "certificate", None)) as cert_path:
            with psycopg2.connect(
                **_connection_kwargs(service, database, cert_path)
            ) as connection:
                connection.set_session(readonly=True)
                with connection.cursor() as cursor:
                    cursor.execute(
                        """
                        SELECT column_name, data_type, is_nullable
                        FROM information_schema.columns
                        WHERE table_schema = %s AND table_name = %s
                        ORDER BY ordinal_position
                        """,
                        (schema, table),
                    )
                    column_info = [
                        {"name": name, "type": data_type, "nullable": nullable == "YES"}
                        for name, data_type, nullable in cursor.fetchall()
                    ]
                    if not column_info:
                        return OperationResult(
                            False,
                            2,
                            f"Table {schema}.{table} was not found.",
                        )

                    cursor.execute(
                        """
                        SELECT a.attname
                        FROM pg_index i
                        JOIN pg_class c ON c.oid = i.indrelid
                        JOIN pg_namespace n ON n.oid = c.relnamespace
                        JOIN unnest(i.indkey) WITH ORDINALITY AS key(attnum, ord) ON true
                        JOIN pg_attribute a ON a.attrelid = c.oid AND a.attnum = key.attnum
                        WHERE i.indisprimary AND n.nspname = %s AND c.relname = %s
                        ORDER BY key.ord
                        """,
                        (schema, table),
                    )
                    primary_key = [row[0] for row in cursor.fetchall()]
                    order_clause = sql.SQL("")
                    if primary_key:
                        order_clause = sql.SQL(" ORDER BY {} ").format(
                            sql.SQL(", ").join(
                                sql.Identifier(name) for name in primary_key
                            )
                        )
                    query = (
                        sql.SQL("SELECT * FROM {}.{}").format(
                            sql.Identifier(schema), sql.Identifier(table)
                        )
                        + order_clause
                        + sql.SQL(" LIMIT %s OFFSET %s")
                    )
                    cursor.execute(query, (page_size + 1, page * page_size))
                    raw_rows = cursor.fetchall()
                    has_more = len(raw_rows) > page_size
                    raw_rows = raw_rows[:page_size]
                    columns = [description[0] for description in cursor.description]
                    rows = [[_display_value(value) for value in row] for row in raw_rows]
    except Exception as exc:
        return OperationResult(
            False, 3, f"Could not load {database}.{schema}.{table}: {exc}"
        )

    return OperationResult(
        True,
        0,
        f"Loaded page {page + 1} of {schema}.{table}.",
        {
            "database": database,
            "schema": schema,
            "table": table,
            "columns": columns,
            "column_info": column_info,
            "rows": rows,
            "page": page,
            "page_size": page_size,
            "has_more": has_more,
            "primary_key": primary_key,
        },
    )


def _display_value(value: Any) -> str:
    if value is None:
        return "NULL"
    if isinstance(value, bytes):
        rendered = "\\x" + value.hex()
    elif isinstance(value, (datetime, date, time)):
        rendered = value.isoformat()
    elif isinstance(value, Decimal):
        rendered = str(value)
    else:
        rendered = str(value)
    if len(rendered) > MAX_CELL_LENGTH:
        return rendered[: MAX_CELL_LENGTH - 1] + "…"
    return rendered
