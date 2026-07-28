from mlox.tui.services.postgres import PostgresSettingsPanel, _format_bytes, settings


class DummyService:
    name = "postgres"


def test_tui_settings_returns_postgres_panel() -> None:
    panel = settings(None, None, DummyService())  # type: ignore[arg-type]

    assert isinstance(panel, PostgresSettingsPanel)


def test_format_bytes_uses_compact_binary_units() -> None:
    assert _format_bytes(0) == "0 B"
    assert _format_bytes(2048) == "2.0 KiB"
