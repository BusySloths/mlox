from __future__ import annotations

from datetime import datetime

from mlox.view.services.otel import _format_timestamp


def test_format_timestamp_preserves_milliseconds() -> None:
    timestamp = datetime(2026, 6, 2, 11, 56, 43, 123456)

    assert _format_timestamp(timestamp) == "2026-06-02T11:56:43.123"
