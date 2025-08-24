import pytest
import json
from pathlib import Path
from mlox.secret_manager import TinySecretManager


@pytest.fixture
def manager():
    """Provides a fresh TinySecretManager instance for each test."""
    return "my_manager"


def test_initialization(manager: str):
    """Test that the manager initializes with no secrets."""
    assert manager == "my_manager"
