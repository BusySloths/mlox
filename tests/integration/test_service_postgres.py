import pytest
import logging
import psycopg2

from mlox.config import load_config, get_stacks_path
from mlox.infra import Infrastructure, Bundle

from .conftest import wait_for_service_ready


pytestmark = pytest.mark.integration

logger = logging.getLogger(__name__)


@pytest.fixture(scope="module")
def install_postgres_service(ubuntu_docker_server):
    """Install and start the Postgres service on the provided server."""
    infra = Infrastructure()
    bundle = Bundle(name=ubuntu_docker_server.ip, server=ubuntu_docker_server)
    infra.bundles.append(bundle)

    config = load_config(get_stacks_path(), "/postgres", "mlox.postgres.16.yaml")

    bundle_added = infra.add_service(ubuntu_docker_server.ip, config, params={})
    if not bundle_added:
        pytest.skip("Failed to add Postgres service from config")

    service = bundle_added.services[-1]

    with ubuntu_docker_server.get_server_connection() as conn:
        service.setup(conn)
        service.spin_up(conn)

    def check_fn():
        conn = psycopg2.connect(
            host=ubuntu_docker_server.ip,
            port=int(service.port),
            user=service.user,
            password=service.pw,
            dbname=service.db,
            sslmode="allow",
        )
        conn.close()
        return {"status": "running"}

    wait_for_service_ready(service, bundle, check_fn=check_fn, retries=40, interval=10)

    yield bundle_added, service

    with ubuntu_docker_server.get_server_connection() as conn:
        try:
            service.spin_down(conn)
        except Exception as e:
            logger.warning(f"Ignoring error during service spin_down for teardown: {e}")
        try:
            service.teardown(conn)
        except Exception as e:
            logger.warning(f"Ignoring error during service teardown: {e}")
    infra.remove_bundle(bundle_added)


def _pg_conn(bundle, service):
    return psycopg2.connect(
        host=bundle.server.ip,
        port=int(service.port),
        user=service.user,
        password=service.pw,
        dbname=service.db,
        sslmode="allow",
    )


def test_postgres_service_is_running(install_postgres_service):
    bundle, service = install_postgres_service
    with _pg_conn(bundle, service) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT 1")
            assert cur.fetchone()[0] == 1


def test_postgres_create_table(install_postgres_service):
    bundle, service = install_postgres_service
    with _pg_conn(bundle, service) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "CREATE TABLE IF NOT EXISTS mlox_test (id SERIAL PRIMARY KEY, name TEXT)"
            )
            cur.execute("INSERT INTO mlox_test (name) VALUES ('mlox')")
            conn.commit()
            cur.execute("SELECT name FROM mlox_test LIMIT 1")
            assert cur.fetchone()[0] == "mlox"
            cur.execute("DROP TABLE mlox_test")
            conn.commit()
