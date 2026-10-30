from types import SimpleNamespace
import requests

from mlox.tui.services.influx import InfluxSettingsPanel, influx_summary, settings


def test_influx_summary_reads_bounded_query_metadata_without_credentials():
    class QueryService:
        def summary(self):
            return {
                "health": {"status": "pass"},
                "measurements": ["spans", "logs", "cpu"],
                "activity": {"spans": 2, "logs": 1},
            }

    service = SimpleNamespace(
        name="InfluxDB 3 Core", state="running",
        service_urls={"InfluxDB": "https://influx"}, database="telemetry",
    )
    summary = influx_summary(service, QueryService())
    assert summary["measurements"] == ["spans", "logs", "cpu"]
    assert summary["activity"] == {"spans": 2, "logs": 1}
    assert "token" not in repr(summary).lower()


def test_influx_settings_returns_dedicated_service_panel():
    service = SimpleNamespace()

    panel = settings(infra=None, bundle=None, service=service)

    assert isinstance(panel, InfluxSettingsPanel)


def test_influx_summary_reports_unauthorized_instead_of_empty_data():
    class QueryService:
        def summary(self):
            response = requests.Response()
            response.status_code = 401
            raise requests.HTTPError("sensitive response details", response=response)

    summary = influx_summary(SimpleNamespace(state="running"), QueryService())
    assert "HTTP 401" in summary["error"]
    assert "sensitive response details" not in repr(summary)
    assert summary["health"]["status"] == "unavailable"
