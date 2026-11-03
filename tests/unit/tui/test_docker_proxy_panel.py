import asyncio
from types import SimpleNamespace

from textual.app import App, ComposeResult
from textual.widgets import DataTable

from mlox.application.result import OperationResult
from mlox.tui.services.docker_proxy import DockerProxyPanel


class ProxyApp(App):
    def __init__(self):
        super().__init__()
        self.service = SimpleNamespace(name='proxy', routes={})
        self.calls = []
        self.workspace = SimpleNamespace(add_proxy_route=self.add, remove_proxy_route=self.remove)

    def compose(self) -> ComposeResult:
        yield DockerProxyPanel(None, None, self.service)

    def add(self, **kwargs):
        self.calls.append(kwargs)
        self.service.routes[kwargs['hostname']] = {'backend': kwargs['backend'], 'tls_mode': kwargs['tls_mode']}
        return OperationResult(True, 0, 'Added')

    def remove(self, **kwargs):
        self.calls.append(kwargs)
        del self.service.routes[kwargs['hostname']]
        return OperationResult(True, 0, 'Removed')


async def _exercise_panel():
    app = ProxyApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        panel = app.query_one(DockerProxyPanel)
        panel._run = lambda operation: panel._finish(operation(app.workspace))
        panel._add_values({'hostname': 'notes.example.org', 'backend': 'https://host.docker.internal:5230',
                           'tls_mode': 'self-signed', 'insecure_backend': 'true', 'backend_host': '192.0.2.1'})
        await pilot.pause(0.2)
        assert app.calls[0]['insecure_backend'] is True
        assert app.calls[0]['backend_host'] == '192.0.2.1'
        assert app.query_one('#proxy-routes', DataTable).row_count == 1
        panel.remove_route()
        await pilot.pause(0.2)
        assert app.calls[1]['hostname'] == 'notes.example.org'
        assert app.query_one('#proxy-routes', DataTable).row_count == 0


def test_proxy_panel_adds_and_removes_routes():
    asyncio.run(_exercise_panel())
