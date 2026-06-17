from types import SimpleNamespace

from mlox.services.kubeflow.k8s import KubeflowService
from mlox.view.services import kubeflow


BASE = {
    "name": "kubeflow",
    "service_config_id": "kubeflow-1.10.1-k3s",
    "template": "/tmp/kubeflow.yaml",
    "target_path": "/tmp/kubeflow",
}


def test_settings_exposes_url_port_and_initial_credentials(monkeypatch):
    calls = []
    fake_streamlit = SimpleNamespace(
        link_button=lambda *args, **kwargs: calls.append(
            ("link_button", args, kwargs)
        ),
        write=lambda *args, **kwargs: calls.append(("write", args, kwargs)),
        code=lambda *args, **kwargs: calls.append(("code", args, kwargs)),
        caption=lambda *args, **kwargs: calls.append(("caption", args, kwargs)),
    )
    monkeypatch.setattr(kubeflow, "st", fake_streamlit)
    service = KubeflowService(**BASE)
    service.service_urls["Kubeflow"] = "https://cluster.example:8443/"
    service.service_ports["Kubeflow"] = 8443

    kubeflow.settings(None, None, service)

    assert (
        "link_button",
        ("Open Kubeflow",),
        {
            "url": "https://cluster.example:8443/",
            "icon": ":material/open_in_new:",
        },
    ) in calls
    assert ("write", ("HTTPS port: `8443`",), {}) in calls
    assert ("code", ("user@example.com",), {}) in calls
    assert ("code", ("12341234",), {}) in calls
