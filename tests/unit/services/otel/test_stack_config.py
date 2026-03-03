from pathlib import Path


def test_otel_stack_uses_expected_versioned_files_and_image() -> None:
    repo_root = Path(__file__).resolve().parents[4]
    stack_config = repo_root / "mlox/services/otel/mlox.otel.0.146.1.yaml"
    compose_config = repo_root / "mlox/services/otel/docker-compose-otel-0.146.1.yaml"

    assert stack_config.exists()
    assert compose_config.exists()

    stack_text = stack_config.read_text(encoding="utf-8")
    compose_text = compose_config.read_text(encoding="utf-8")

    assert 'version: "0.146.1"' in stack_text
    assert "docker-compose-otel-0.146.1.yaml" in stack_text
    assert "otel-collector-config-0.146.1.yaml" in stack_text
    assert "grafana_cloud_endpoint: ${MLOX_GRAFANA_CLOUD_ENDPOINT}" in stack_text
    assert "grafana_cloud_key: ${MLOX_GRAFANA_CLOUD_KEY}" in stack_text
    assert "otel/opentelemetry-collector-contrib:0.146.1" in compose_text
    assert "MY_OTEL_GRAFANA_CLOUD_ENDPOINT=${OTEL_GRAFANA_CLOUD_ENDPOINT}" in compose_text
    assert "MY_OTEL_GRAFANA_CLOUD_KEY=${OTEL_GRAFANA_CLOUD_KEY}" in compose_text
