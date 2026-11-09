import asyncio
from types import SimpleNamespace

from textual.app import App, ComposeResult
from textual.widgets import Button, DataTable

from mlox.application.result import OperationResult
from mlox.application.use_cases.apps import UNPROXIED_APPS, describe_apps, open_app
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
    assert empty.data['proxies'][0]['id'] == UNPROXIED_APPS
    assert empty.data['apps_by_proxy'][UNPROXIED_APPS] == []


def test_apps_grouped_by_explicit_and_unambiguous_legacy_routes():
    from mlox.services.docker_proxy.docker import DockerProxyService

    notes = _service('Notes', {ServiceCapability.APP, ServiceCapability.WEB_UI}, 'https://1.2.3.4:5230')
    wiki = _service('Wiki', {ServiceCapability.APP, ServiceCapability.WEB_UI}, 'https://1.2.3.4:3000')
    no_proxy = _service('Direct', {ServiceCapability.APP, ServiceCapability.WEB_UI}, 'https://1.2.3.4:8080')
    gateway = DockerProxyService(name='Gateway', service_config_id='docker-proxy-1-docker', template='docker_proxy/mlox.docker_proxy.yaml', target_path='/tmp/proxy')
    gateway.routes = {'notes.example.org': {'backend': 'https://host.docker.internal:5230'},
                      'wiki.example.org': {'backend': 'http://unrelated.example:9000', 'service_uuid': wiki.uuid}}
    bundle = SimpleNamespace(name='One', server=SimpleNamespace(ip='1.2.3.4'), services=[notes, wiki, no_proxy, gateway])
    data = describe_apps(SimpleNamespace(bundles=[bundle])).data
    assert [row['name'] for row in data['apps_by_proxy'][gateway.uuid]] == ['Notes', 'Wiki']
    assert [row['name'] for row in data['apps_by_proxy'][UNPROXIED_APPS]] == ['Direct']
    assert data['proxies'][0]['name'] == 'No proxy'
    assert data['proxies'][1]['app_count'] == 2
    assert data['apps_by_proxy'][gateway.uuid][0]['proxy_urls'] == ['https://notes.example.org']


def test_ambiguous_legacy_route_never_guesses():
    from mlox.services.docker_proxy.docker import DockerProxyService

    a = _service('A', {ServiceCapability.APP, ServiceCapability.WEB_UI}, 'https://1.2.3.4:5230')
    b = _service('B', {ServiceCapability.APP, ServiceCapability.WEB_UI}, 'https://1.2.3.4:5230')
    gateway = DockerProxyService(name='Gateway', service_config_id='docker-proxy-1-docker', template='docker_proxy/mlox.docker_proxy.yaml', target_path='/tmp/proxy')
    gateway.routes = {'notes.example.org': {'backend': 'https://host.docker.internal:5230'}}
    bundle = SimpleNamespace(name='One', server=SimpleNamespace(ip='1.2.3.4'), services=[a, b, gateway])
    data = describe_apps(SimpleNamespace(bundles=[bundle])).data
    assert data['apps_by_proxy'][gateway.uuid] == []
    assert len(data['apps_by_proxy'][UNPROXIED_APPS]) == 2


def test_open_app_prefers_selected_proxy_url():
    opened = []
    result = open_app({'url': 'https://direct:5230', 'proxy_urls': ['https://notes.example.org']}, opener=lambda url: opened.append(url))
    assert result.success and opened == ['https://notes.example.org']


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
    monkeypatch.setattr('mlox.tui.screens.dashboard.apps_panel.open_app', lambda row: calls.append(row['service_ref']) or OperationResult(True, 0, 'Opened'))
    # Data is local here; avoid launching background workers in the test harness.
    monkeypatch.setattr(AppsPanel, 'load', lambda panel: panel._show_result(describe_apps(panel.app.workspace.infrastructure)))
    async with app.run_test() as pilot:
        panel = app.query_one(AppsPanel)
        panel.selection = SelectionInfo(type='root')
        await pilot.pause()
        assert panel.display
        table = app.query_one('#apps-table', DataTable)
        proxies = app.query_one('#apps-proxy-table', DataTable)
        assert proxies.row_count == 1
        assert 'No proxy' in ' '.join(str(cell) for cell in proxies.get_row_at(0))
        assert table.row_count == 1
        assert 'Notes' in ' '.join(str(cell) for cell in table.get_row_at(0))
        panel.open_app(Button.Pressed(app.query_one('#open-app', Button)))
        assert calls == [service]
        panel.selection = SelectionInfo(type='bundle', bundle=bundle, server=bundle.server)
        await pilot.pause()
        assert not panel.display


def test_apps_tab_lists_apps_and_is_visible_at_project_root(monkeypatch):
    asyncio.run(_exercise_apps_tab(monkeypatch))


async def _exercise_proxy_selection(monkeypatch):
    from mlox.services.docker_proxy.docker import DockerProxyService

    notes = _service('Notes', {ServiceCapability.APP, ServiceCapability.WEB_UI}, 'https://1.2.3.4:5230')
    direct = _service('Direct', {ServiceCapability.APP, ServiceCapability.WEB_UI}, 'https://1.2.3.4:8080')
    gateway = DockerProxyService(name='Gateway', service_config_id='docker-proxy-1-docker', template='docker_proxy/mlox.docker_proxy.yaml', target_path='/tmp/proxy')
    gateway.routes = {'notes.example.org': {'backend': 'https://host.docker.internal:5230', 'service_uuid': notes.uuid}}
    bundle = SimpleNamespace(name='One', server=SimpleNamespace(ip='1.2.3.4'), services=[notes, direct, gateway])

    class AppsTestApp(App):
        def __init__(self):
            super().__init__()
            self.workspace = SimpleNamespace(infrastructure=SimpleNamespace(bundles=[bundle]))
        def compose(self) -> ComposeResult:
            yield AppsPanel()

    monkeypatch.setattr(AppsPanel, 'load', lambda panel: panel._show_result(describe_apps(panel.app.workspace.infrastructure)))
    app = AppsTestApp()
    async with app.run_test() as pilot:
        panel = app.query_one(AppsPanel)
        panel.selection = SelectionInfo(type='root')
        await pilot.pause()
        app_table = app.query_one('#apps-table', DataTable)
        proxy_table = app.query_one('#apps-proxy-table', DataTable)
        assert proxy_table.row_count == 2
        assert 'Direct' in str(app_table.get_row_at(0))
        proxy_table.move_cursor(row=1)
        await pilot.pause()
        assert 'Notes' in str(app_table.get_row_at(0))
        assert 'https://notes.example.org' in str(app_table.get_row_at(0))


def test_selecting_proxy_filters_the_app_table(monkeypatch):
    asyncio.run(_exercise_proxy_selection(monkeypatch))


def test_proxied_app_url_retains_direct_ui_path():
    from mlox.services.docker_proxy.docker import DockerProxyService

    service = _service('Vault', {ServiceCapability.APP}, 'https://192.0.2.1:8200/ui/')
    gateway = DockerProxyService(name='Gateway', service_config_id='docker-proxy-1-docker', template='docker_proxy/mlox.docker_proxy.yaml', target_path='/tmp/proxy')
    gateway.routes = {'vault.example.org': {'backend': 'https://host.docker.internal:8200', 'service_uuid': service.uuid}}
    bundle = SimpleNamespace(name='One', server=SimpleNamespace(ip='192.0.2.1'), services=[service, gateway])
    row = describe_apps(SimpleNamespace(bundles=[bundle])).data['apps_by_proxy'][gateway.uuid][0]
    assert row['proxy_urls'] == ['https://vault.example.org/ui/']
