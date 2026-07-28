from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from mlox.application.use_cases import postgres


class DummyService:
    service_urls = {"Postgres IP": "database.example.test"}
    port = "5433"
    user = "mlox"
    pw = "secret"


def test_connection_kwargs_use_service_endpoint_and_tls_certificate() -> None:
    kwargs = postgres._connection_kwargs(DummyService(), "analytics", "/tmp/ca.pem")

    assert kwargs == {
        "host": "database.example.test",
        "port": 5433,
        "dbname": "analytics",
        "user": "mlox",
        "password": "secret",
        "connect_timeout": 5,
        "sslmode": "verify-full",
        "sslrootcert": "/tmp/ca.pem",
    }


def test_display_value_formats_null_binary_dates_and_long_values() -> None:
    assert postgres._display_value(None) == "NULL"
    assert postgres._display_value(b"\x01\xff") == "\\x01ff"
    assert postgres._display_value(Decimal("12.30")) == "12.30"
    assert postgres._display_value(datetime(2026, 7, 28, 10, 30)) == "2026-07-28T10:30:00"
    assert postgres._display_value("x" * 600).endswith("…")
    assert len(postgres._display_value("x" * 600)) == postgres.MAX_CELL_LENGTH


def test_catalog_reports_missing_driver_as_operation_failure(monkeypatch) -> None:
    def unavailable():
        raise RuntimeError("driver unavailable")

    monkeypatch.setattr(postgres, "_load_driver", unavailable)

    result = postgres.load_postgres_catalog(DummyService())

    assert not result.success
    assert "driver unavailable" in result.message
