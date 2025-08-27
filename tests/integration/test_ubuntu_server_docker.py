import pytest

# Mark this module as an integration test
pytestmark = pytest.mark.integration


def test_backend_is_running(ubuntu_docker_server):
    """Ensure the Docker backend is installed and running on the server."""
    assert "docker" in ubuntu_docker_server.backend
    status = ubuntu_docker_server.get_backend_status()
    assert status.get("docker.is_running")
