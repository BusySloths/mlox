import json
from contextlib import nullcontext
from types import SimpleNamespace

import pytest
import requests

from scripts import test_influx as diagnostic


@pytest.mark.parametrize("same", [True, False])
def test_diagnostic_compares_tokens_without_printing_them(monkeypatch, same):
    stored = "workspace-secret"
    deployed = stored if same else "bootstrap-secret"
    calls = []

    def query(connection, token):
        calls.append(token)
        return "HTTP 401"

    monkeypatch.setattr(diagnostic, "query_status", query)
    commands = []

    def execute(conn, command, *, group, sudo, description):
        from mlox.execution.base import TaskGroup
        assert group == TaskGroup.SECURITY_ASSETS
        assert sudo is True
        commands.append(command)
        return json.dumps({"token": deployed})

    service = SimpleNamespace(
        target_path="/srv/influx",
        get_secrets=lambda: {"influx_connection": {"token": stored}},
        exec=SimpleNamespace(execute=execute),
    )
    bundle = SimpleNamespace(server=SimpleNamespace(get_server_connection=lambda: nullcontext(None)))
    output = "\n".join(diagnostic.diagnose(bundle, service))
    assert calls == [stored, deployed]
    assert commands[0] == (
        "sudo docker exec influxdb3 cat -- "
        "/run/secrets/influxdb3-admin-token"
    )
    assert f"tokens match: {'yes' if same else 'NO'}" in output
    assert stored not in output and deployed not in output


def test_diagnostic_reports_http_status_without_response_secrets(monkeypatch):
    def query(*args, **kwargs):
        response = requests.Response()
        response.status_code = 401
        raise requests.HTTPError("secret response", response=response)

    monkeypatch.setattr(diagnostic.InfluxClient, "query", query)
    assert diagnostic.query_status(
        {"url": "https://influx.example", "database": "telemetry"}, "secret"
    ) == "HTTP 401"
