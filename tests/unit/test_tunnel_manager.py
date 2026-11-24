from contextlib import contextmanager
from threading import Event, Thread

import pytest

from mlox.application.tunnels import TunnelManager
from mlox.server import ServerCapability
from mlox.tunnel import TunnelBinding, TunnelEndpoint, TunnelPlan


def test_composite_tunnel_group_closes_all_and_clears_secrets():
    closed = []

    class Server:
        capabilities = {ServerCapability.TUNNEL}
        @contextmanager
        def open_tunnel(self, endpoint):
            try:
                yield TunnelBinding(endpoint, 15000 + endpoint.remote_port % 1000)
            finally:
                closed.append(endpoint.server_uuid)

    endpoints = (TunnelEndpoint("pg", "db", "one", "127.0.0.1", 5432),
                 TunnelEndpoint("s3", "api", "two", "127.0.0.1", 9000))
    manager = TunnelManager(lambda _: Server())
    group = manager.open(TunnelPlan("ducklake", endpoints), lambda _: {"password": "secret"})
    assert "secret" not in repr(group)
    manager.close(group.id)
    assert closed == ["two", "one"]
    assert group.secrets == {}


def test_failed_group_closes_already_open_tunnels():
    closed = []

    class Server:
        capabilities = {ServerCapability.TUNNEL}
        @contextmanager
        def open_tunnel(self, endpoint):
            try:
                yield TunnelBinding(endpoint, 15432)
            finally:
                closed.append(endpoint.name)

    endpoints = (TunnelEndpoint("pg", "db", "one", "127.0.0.1", 5432),
                 TunnelEndpoint("s3", "api", "missing", "127.0.0.1", 9000))
    manager = TunnelManager(lambda uuid: Server() if uuid == "one" else None)
    with pytest.raises(ValueError, match="does not support"):
        manager.open(TunnelPlan("ducklake", endpoints), lambda _: {})
    assert closed == ["db"]


def test_tunnel_expires_and_closes():
    closed = Event()

    class Server:
        capabilities = {ServerCapability.TUNNEL}
        @contextmanager
        def open_tunnel(self, endpoint):
            try:
                yield TunnelBinding(endpoint, 15432)
            finally:
                closed.set()

    endpoint = TunnelEndpoint("pg", "db", "one", "127.0.0.1", 5432)
    manager = TunnelManager(lambda _: Server())
    group = manager.open(TunnelPlan("pg", (endpoint,)), lambda _: {"password": "secret"}, duration=0.05)
    assert closed.wait(2)
    manager.close_all()
    assert group.secrets == {}


def test_shutdown_prevents_opening_after_exit():
    manager = TunnelManager(lambda _: None)
    endpoint = TunnelEndpoint("pg", "db", "one", "127.0.0.1", 5432)
    manager.shutdown()
    with pytest.raises(RuntimeError, match="shut down"):
        manager.open(TunnelPlan("pg", (endpoint,)), lambda _: {})


def test_pending_open_does_not_block_status_or_shutdown_and_is_cleaned_up():
    started, release, closed = Event(), Event(), Event()

    class Server:
        capabilities = {ServerCapability.TUNNEL}
        @contextmanager
        def open_tunnel(self, endpoint):
            started.set()
            assert release.wait(2)
            try:
                yield TunnelBinding(endpoint, 15432)
            finally:
                closed.set()

    endpoint = TunnelEndpoint("pg", "db", "one", "127.0.0.1", 5432)
    manager = TunnelManager(lambda _: Server())
    errors = []
    def open_group():
        try:
            manager.open(TunnelPlan("pg", (endpoint,)), lambda _: {})
        except Exception as exc:
            errors.append(exc)
    worker = Thread(target=open_group)
    worker.start()
    assert started.wait(2)
    assert manager.list_groups() == ()
    manager.shutdown()
    release.set()
    worker.join(2)
    assert not worker.is_alive() and closed.is_set()
    assert len(errors) == 1 and "shut down" in str(errors[0])
