import pytest
import logging

# Mark this module as an integration test
pytestmark = pytest.mark.integration

logger = logging.getLogger(__name__)


def test_dummy_service():
    logger.info("Testing a dummy service...")
    assert True
