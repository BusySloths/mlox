import streamlit as st

from mlox.services.postgres.docker import PostgresDockerService
from mlox.infra import Infrastructure, Bundle

import os
import tempfile
from contextlib import contextmanager
from typing import Any, Dict, Iterator, List, Tuple


def setup(infra: Infrastructure, bundle: Bundle):
    params = dict()

    database_name = st.text_input("Database Name", value="mlox")
    params["${POSTGRES_DB}"] = database_name
    return params


def _load_psycopg2() -> Any:
    try:
        import psycopg2
    except ImportError as exc:
        raise RuntimeError(
            "Postgres catalog browsing requires psycopg2-binary. "
            "Install the mlox dev extra or install psycopg2-binary."
        ) from exc
    return psycopg2


@contextmanager
def _postgres_cert_file(certificate: str | None) -> Iterator[str | None]:
    if not certificate:
        yield None
        return

    cert_path = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".pem") as cert:
            cert.write(certificate)
            cert_path = cert.name
        yield cert_path
    finally:
        if cert_path and os.path.exists(cert_path):
            os.remove(cert_path)


def _postgres_connection_kwargs(
    service: PostgresDockerService,
    database: str,
    sslrootcert: str | None,
) -> Dict[str, Any]:
    kwargs: Dict[str, Any] = {
        "host": service.service_urls.get("Postgres IP") or service.service_urls.get("host"),
        "port": int(service.port),
        "dbname": database,
        "user": service.user,
        "password": service.pw,
        "connect_timeout": 5,
        "sslmode": "verify-full" if sslrootcert else "require",
    }
    if sslrootcert:
        kwargs["sslrootcert"] = sslrootcert
    return kwargs


def _fetch_postgres_catalog(
    service: PostgresDockerService,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, str]]]:
    psycopg2 = _load_psycopg2()
    databases: List[Dict[str, Any]] = []
    tables: List[Dict[str, Any]] = []
    errors: List[Dict[str, str]] = []

    with _postgres_cert_file(service.certificate) as sslrootcert:
        with psycopg2.connect(
            **_postgres_connection_kwargs(service, service.db, sslrootcert)
        ) as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT datname, pg_get_userbyid(datdba) AS owner,
                           pg_size_pretty(pg_database_size(datname)) AS size
                    FROM pg_database
                    WHERE datistemplate = false
                      AND datallowconn = true
                    ORDER BY datname;
                    """
                )
                databases = [
                    {"database": name, "owner": owner, "size": size}
                    for name, owner, size in cursor.fetchall()
                ]

        for database in databases:
            database_name = database["database"]
            try:
                with psycopg2.connect(
                    **_postgres_connection_kwargs(service, database_name, sslrootcert)
                ) as conn:
                    with conn.cursor() as cursor:
                        cursor.execute(
                            """
                            SELECT table_schema, table_name, table_type
                            FROM information_schema.tables
                            WHERE table_schema NOT IN ('pg_catalog', 'information_schema')
                            ORDER BY table_schema, table_name;
                            """
                        )
                        tables.extend(
                            {
                                "database": database_name,
                                "schema": schema,
                                "table": table,
                                "type": table_type,
                            }
                            for schema, table, table_type in cursor.fetchall()
                        )
            except psycopg2.Error as exc:
                errors.append({"database": database_name, "error": str(exc).strip()})

    return databases, tables, errors


def settings(infra: Infrastructure, bundle: Bundle, service: PostgresDockerService):
    st.header(f"Settings for service {service.name}")
    # st.write(f"IP: {bundle.server.ip}")

    st.write(f"user: {service.user}")
    st.write(f'password: "{service.pw}"')
    st.write(f'database: "{service.db}"')
    st.write(f'port: "{service.port}"')

    st.write(f'url: "{service.service_urls["Postgres"]}"')

    catalog_key = f"postgres-catalog-{service.uuid}"
    st.subheader("Database catalog")
    if st.button("Refresh catalog", key=f"postgres-refresh-catalog-{service.uuid}"):
        try:
            with st.spinner("Inspecting Postgres catalog..."):
                st.session_state[catalog_key] = {
                    "result": _fetch_postgres_catalog(service),
                    "error": None,
                }
        except RuntimeError as exc:
            st.session_state[catalog_key] = {"result": None, "error": str(exc)}
        except Exception as exc:
            st.session_state[catalog_key] = {
                "result": None,
                "error": f"Could not inspect Postgres catalog: {exc}",
            }

    catalog = st.session_state.get(catalog_key)
    if not catalog:
        st.caption("Click refresh to list databases and user tables.")
        return

    if catalog["error"]:
        st.warning(catalog["error"])
        return

    databases, tables, errors = catalog["result"]

    st.write("Databases")
    if databases:
        st.dataframe(databases, hide_index=True, use_container_width=True)
    else:
        st.info("No databases found.")

    st.write("Tables")
    if tables:
        st.dataframe(tables, hide_index=True, use_container_width=True)
    else:
        st.info("No user tables found.")

    if errors:
        st.write("Database inspection errors")
        st.dataframe(errors, hide_index=True, use_container_width=True)
