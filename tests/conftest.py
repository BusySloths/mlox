import os
import pytest


def pytest_addoption(parser):
    parser.addoption(
        "--run-integration",
        action="store_true",
        default=False,
        help="Run integration tests (disabled by default).",
    )


def pytest_collection_modifyitems(config, items):
    run_integration = config.getoption("--run-integration") or os.getenv(
        "RUN_INTEGRATION"
    ) in ("1", "true", "True")
    if run_integration:
        return

    skip_marker = pytest.mark.skip(
        reason="Integration tests disabled. Use --run-integration or set RUN_INTEGRATION=1 to enable."
    )
    for item in items:
        if "integration" in item.keywords:
            item.add_marker(skip_marker)
