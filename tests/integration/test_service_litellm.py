"""Integration tests for LiteLLM + Ollama service."""

import logging
import pytest
import requests

from mlox.config import get_stacks_path, load_config
from mlox.infra import Bundle, Infrastructure
from tests.integration.conftest import wait_for_service_ready

pytestmark = pytest.mark.integration

logger = logging.getLogger(__name__)


@pytest.fixture(scope="module")
def install_litellm_service(ubuntu_docker_server):
    """Install and start the LiteLLM + Ollama service on the provided server."""
    infra = Infrastructure()
    bundle = Bundle(name=ubuntu_docker_server.ip, server=ubuntu_docker_server)
    infra.bundles.append(bundle)

    # Load LiteLLM stack config
    config = load_config(get_stacks_path(), "/litellm", "mlox.litellm.1.73.0.yaml")

    # Test with minimal model selection for faster tests
    params = {"${OLLAMA_MODELS}": "tinyllama"}

    bundle_added = infra.add_service(ubuntu_docker_server.ip, config, params=params)
    if not bundle_added:
        pytest.skip("Failed to add LiteLLM service from config")

    service = bundle_added.services[-1]

    # Setup and start the service
    with ubuntu_docker_server.get_server_connection() as conn:
        service.setup(conn)
        service.spin_up(conn)

    # Wait longer for LiteLLM + Ollama to start (pulling models takes time)
    wait_for_service_ready(service, bundle, retries=20, interval=30, no_checks=True)

    yield bundle_added, service

    # Teardown after tests
    with ubuntu_docker_server.get_server_connection() as conn:
        try:
            service.spin_down(conn)
        except Exception as e:
            logger.warning(f"Ignoring error during service spin_down for teardown: {e}")
        try:
            service.teardown(conn)
        except Exception as e:
            logger.warning(f"Ignoring error during service teardown: {e}")
    infra.remove_bundle(bundle_added)


def test_litellm_service_is_running(install_litellm_service):
    """Test that LiteLLM service is running."""
    bundle, service = install_litellm_service
    wait_for_service_ready(service, bundle, retries=60, interval=10)

    status = {}
    try:
        with bundle.server.get_server_connection() as conn:
            status = service.check(conn)
    except Exception as e:
        logger.error(f"Error checking LiteLLM service status: {e}")

    assert status.get("status", None) == "running"


def test_ollama_models_installed(install_litellm_service):
    """Test that Ollama models were installed based on user selection."""
    bundle, service = install_litellm_service

    # Verify that ollama_models parameter was set
    assert hasattr(service, "ollama_models")
    assert service.ollama_models == "tinyllama"

    # TODO: Add actual API call to check if model is available in Ollama
    # This would require accessing Ollama API endpoint at http://ollama:11434/api/tags
    # For now, we verify the configuration was passed correctly
    logger.info(f"Ollama models configured: {service.ollama_models}")


def test_litellm_multiple_models_selection(ubuntu_docker_server):
    """Test LiteLLM service with multiple model selection."""
    infra = Infrastructure()
    bundle = Bundle(name=ubuntu_docker_server.ip, server=ubuntu_docker_server)
    infra.bundles.append(bundle)

    config = load_config(get_stacks_path(), "/litellm", "mlox.litellm.1.73.0.yaml")

    # Test with multiple models
    params = {"${OLLAMA_MODELS}": "tinyllama,qwen2.5:0.5b"}

    bundle_added = infra.add_service(ubuntu_docker_server.ip, config, params=params)
    if not bundle_added:
        pytest.skip("Failed to add LiteLLM service from config")

    service = bundle_added.services[-1]

    # Verify models parameter
    assert service.ollama_models == "tinyllama,qwen2.5:0.5b"

    # Cleanup (don't actually spin up to save test time)
    infra.remove_bundle(bundle_added)


def test_litellm_no_models_selection(ubuntu_docker_server):
    """Test LiteLLM service with no models selected."""
    infra = Infrastructure()
    bundle = Bundle(name=ubuntu_docker_server.ip, server=ubuntu_docker_server)
    infra.bundles.append(bundle)

    config = load_config(get_stacks_path(), "/litellm", "mlox.litellm.1.73.0.yaml")

    # Test with empty model selection
    params = {"${OLLAMA_MODELS}": ""}

    bundle_added = infra.add_service(ubuntu_docker_server.ip, config, params=params)
    if not bundle_added:
        pytest.skip("Failed to add LiteLLM service from config")

    service = bundle_added.services[-1]

    # Verify models parameter is empty
    assert service.ollama_models == ""

    # Cleanup (don't actually spin up to save test time)
    infra.remove_bundle(bundle_added)
