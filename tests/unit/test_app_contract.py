from types import SimpleNamespace

import pytest

from mlox.application.use_cases.apps import describe_apps
from mlox.application.use_cases.services import get_service_web_ui_address
from mlox.service import AbstractAppService, AbstractWebUIService, ServiceCapability


class App(AbstractAppService):
    def __init__(self, url):
        self.service_url = url


@pytest.mark.parametrize(("url", "app_host", "proxy_host", "expected"), [
    ("https://192.0.2.1:5230/ui", "192.0.2.1", "192.0.2.1", {"url": "https://host.docker.internal:5230", "host_header": "192.0.2.1"}),
    ("https://192.0.2.2:5230/ui", "192.0.2.2", "192.0.2.1", {"url": "https://192.0.2.2:5230", "host_header": ""}),
    ("http://localhost:8080/", "192.0.2.2", "192.0.2.1", {"url": "http://192.0.2.2:8080", "host_header": "localhost"}),
    ("https://notes.example.org/", "192.0.2.2", "192.0.2.1", {"url": "https://notes.example.org:443", "host_header": ""}),
    ("http://localhost:8080/", "", "", {}),
    ("https://user:secret@example.org/", "", "", {}),
])
def test_proxy_endpoint_is_a_suggestion_for_the_proxy_context(url, app_host, proxy_host, expected):
    assert App(url).get_proxy_endpoint(app_host=app_host, proxy_host=proxy_host) == expected


def test_web_ui_contract_remains_a_compatibility_alias():
    assert AbstractWebUIService is AbstractAppService
    old_plugin = SimpleNamespace(name="Old", uuid="old", state="running", capabilities={ServiceCapability.WEB_UI}, get_web_ui_address=lambda: "https://old.example")
    infra = SimpleNamespace(bundles=[SimpleNamespace(name="host", server=SimpleNamespace(ip="192.0.2.1"), services=[old_plugin])])
    assert get_service_web_ui_address(old_plugin).data["url"] == "https://old.example"
    assert describe_apps(infra).data["apps"][0]["id"] == "old"


def test_airflow_proxy_endpoint_preserves_public_host_header():
    from mlox.services.airflow.docker import AirflowDockerService

    service = AirflowDockerService(name="airflow", service_config_id="airflow-3.1.3-docker", template="x", target_path="/tmp/airflow", path_dags="/tmp/dags", path_output="/tmp/output", ui_user="user", ui_pw="pass", port="1099")
    service.service_urls["Airflow UI"] = "https://192.0.2.1:1099"
    assert service.get_proxy_endpoint(app_host="192.0.2.1", proxy_host="192.0.2.1") == {
        "url": "https://host.docker.internal:1099", "host_header": "",
    }
