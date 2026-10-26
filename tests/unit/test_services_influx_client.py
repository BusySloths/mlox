from __future__ import annotations

import base64

import pytest

from mlox.services.influx.client import InfluxClient


def test_from_env_returns_none_without_runtime_binding():
    assert InfluxClient.from_env({}) is None


def test_from_env_validates_complete_binding():
    with pytest.raises(ValueError, match="URL and token"):
        InfluxClient.from_env({"MLOX_INFLUX_URL": "https://influx"})


def test_from_env_reads_certificate_without_exposing_token():
    client = InfluxClient.from_env(
        {
            "MLOX_INFLUX_URL": "https://influx.example",
            "MLOX_INFLUX_TOKEN": "very-secret-token",
            "MLOX_INFLUX_DATABASE": "telemetry",
            "MLOX_INFLUX_CERTIFICATE_B64": base64.b64encode(b"certificate").decode(),
        }
    )
    assert client is not None
    assert client.certificate == b"certificate"
    assert "very-secret-token" not in repr(client)


def test_from_secret_manager_resolves_name_to_service_secret():
    class Manager:
        def load_secret(self, name):
            if name == "MLOX_SERVICE_NAME_UUID_MAP":
                return {"influx": "uuid"}
            return {"influx_connection": {"url": "https://influx", "token": "token", "database": "db"}}

    client = InfluxClient.from_secret_manager(Manager(), "influx")
    assert client.url == "https://influx"
    assert client.database == "db"
