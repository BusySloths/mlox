from __future__ import annotations

import base64
from pathlib import Path
from types import SimpleNamespace

import pytest
import requests

from mlox.services.influx.client import InfluxClient


@pytest.mark.parametrize("fail", [False, True])
def test_request_uses_ca_file_and_cleans_up(monkeypatch, fail):
    certificate = b"-----BEGIN CERTIFICATE-----\ntest CA\n-----END CERTIFICATE-----\n"
    client = InfluxClient("https://influx.example", "secret", certificate=certificate)
    paths = []

    def request(method, url, **kwargs):
        ca_path = Path(kwargs["verify"])
        paths.append(ca_path)
        assert ca_path.read_bytes() == certificate
        # Exercise Requests' actual path check, which rejected raw PEM bytes.
        connection = SimpleNamespace()
        requests.adapters.HTTPAdapter().cert_verify(connection, url, kwargs["verify"], None)
        assert connection.cert_reqs == "CERT_REQUIRED"
        assert kwargs["headers"]["Authorization"] == "Bearer secret"
        if fail:
            raise requests.exceptions.SSLError("TLS validation failed")
        return SimpleNamespace(raise_for_status=lambda: None, json=lambda: {"status": "ok"})

    monkeypatch.setattr(requests, "request", request)
    if fail:
        with pytest.raises(requests.exceptions.SSLError):
            client.health()
    else:
        assert client.health() == {"status": "ok"}
    assert len(paths) == 1
    assert not paths[0].exists()
    assert not paths[0].parent.exists()


def test_request_without_custom_ca_keeps_verification_enabled(monkeypatch):
    def request(method, url, **kwargs):
        assert kwargs["verify"] is True
        return SimpleNamespace(raise_for_status=lambda: None, json=lambda: {"status": "ok"})

    monkeypatch.setattr(requests, "request", request)
    assert InfluxClient("https://influx.example", "secret").health() == {"status": "ok"}


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
