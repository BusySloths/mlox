from types import SimpleNamespace

from mlox.tui.services.influx import influx_summary


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
