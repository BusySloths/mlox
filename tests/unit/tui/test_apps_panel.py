import asyncio
from types import SimpleNamespace

from textual.app import App, ComposeResult
from textual.widgets import Button, DataTable

from mlox.application.result import OperationResult
from mlox.application.use_cases.apps import describe_apps
from mlox.service import ServiceCapability
from mlox.tui.screens.dashboard.apps_panel import AppsPanel
from mlox.tui.screens.dashboard.model import SelectionInfo


def _service(name, capabilities, url='', state='running'):
    return SimpleNamespace(name=name, uuid=name, state=state, capabilities=capabilities,
                           get_web_ui_address=lambda: url)


def test_describe_apps_filters_and_summarizes_across_bundles():
    memos = _service('Notes', {ServiceCapability.APP, ServiceCapability.WEB_UI}, 'https://notes.example.org')
    stopped = _service('Wiki', {ServiceCapability.APP, ServiceCapability.WEB_UI}, state='stopped')
    infra = SimpleNamespace(bundles=[
        SimpleNamespace(name='One', server=SimpleNamespace(ip='1.2.3.4'), services=[memos, _service('Database', {ServiceCapability.DATABASE})]),
        SimpleNamespace(name='Two', server=SimpleNamespace(ip='1.2.3.5'), services=[stopped]),
    ])
    result = describe_apps(infra)
    assert result.success
    assert [row['name'] for row in result.data['apps']] == ['Notes', 'Wiki']
    assert result.data['metrics'] == {'total': 2, 'running': 1, 'stopped': 1, 'with_url': 1}
    assert result.data['apps'][0]['url'] == 'https://notes.example.org'
    assert not describe_apps(None).success
    empty = describe_apps(SimpleNamespace(bundles=[]))
    assert empty.success and empty.data['apps'] == []
    assert empty.data['metrics']['total'] == 0


async def _exercise_apps_tab(monkeypatch):
    service = _service('Notes', {ServiceCapability.APP, ServiceCapability.WEB_UI}, 'https://notes.example.org')
    bundle = SimpleNamespace(name='dev', server=SimpleNamespace(ip='10.0.0.5', backend=['docker'], state='running'), services=[service])
    class AppsTestApp(App):
        def __init__(self):
            super().__init__()
            self.workspace = SimpleNamespace(infrastructure=SimpleNamespace(bundles=[bundle]))

        def compose(self) -> ComposeResult:
            yield AppsPanel()

    app = AppsTestApp()
    calls = []
    monkeypatch.setattr('mlox.tui.screens.dashboard.apps_panel.open_service_web_ui', lambda item: calls.append(item) or OperationResult(True, 0, 'Opened'))
    # Data is local here; avoid launching background workers in the test harness.
    monkeypatch.setattr(AppsPanel, 'load', lambda panel: panel._show_result(describe_apps(panel.app.workspace.infrastructure)))
    async with app.run_test() as pilot:
        panel = app.query_one(AppsPanel)
        panel.selection = SelectionInfo(type='root')
        await pilot.pause()
        assert panel.display
        table = app.query_one('#apps-table', DataTable)
        assert table.row_count == 1
        assert 'Notes' in ' '.join(str(cell) for cell in table.get_row_at(0))
        panel.open_app(Button.Pressed(app.query_one('#open-app', Button)))
        assert calls == [service]
        panel.selection = SelectionInfo(type='bundle', bundle=bundle, server=bundle.server)
        await pilot.pause()
        assert not panel.display


def test_apps_tab_lists_apps_and_is_visible_at_project_root(monkeypatch):
    asyncio.run(_exercise_apps_tab(monkeypatch))
