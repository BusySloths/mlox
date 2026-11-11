import asyncio

from textual.app import App, ComposeResult

from mlox.application.result import OperationResult
from mlox.application.use_cases.models import PASSWORD_MASK
from mlox.tui.screens.dashboard import models_panel
from mlox.tui.screens.dashboard.models_panel import ModelsPanel

EXAMPLE = "curl -k -u 'user:s3cret' \\\n  https://endpoint.example/invocations"


def test_models_panel_masks_the_password_but_copies_and_calls_with_it(monkeypatch):
    calls = []
    monkeypatch.setattr(
        models_panel,
        "call_model_example",
        lambda example: calls.append(example) or OperationResult(True, 0, "HTTP 200", {"body": "{}"}),
    )

    class ModelsTestApp(App):
        copied: list[str] = []

        def compose(self) -> ComposeResult:
            yield ModelsPanel()

        def copy_to_clipboard(self, text: str) -> None:
            self.copied.append(text)

    async def exercise() -> None:
        app = ModelsTestApp()
        async with app.run_test() as pilot:
            panel = app.query_one(ModelsPanel)
            panel._show_example(EXAMPLE)
            assert "s3cret" not in panel.example.text
            assert PASSWORD_MASK in panel.example.text

            assert panel.copy_current_example()
            assert app.copied == [EXAMPLE]

            assert panel.call_current_example()
            await pilot.pause()
            await app.workers.wait_for_complete()
            await pilot.pause()
            assert calls == [EXAMPLE]
            assert "s3cret" not in panel.example.text

    asyncio.run(exercise())
