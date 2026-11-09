import asyncio
from types import SimpleNamespace

from textual.app import App, ComposeResult
from textual.widgets import Button, DataTable, Select

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


async def _open_add_route_with_optional_service():
    app = ProxyApp()
    service = SimpleNamespace(name="backend", uuid="backend-1")
    infra = SimpleNamespace(bundles=[SimpleNamespace(name="host", services=[service])])
    async with app.run_test() as pilot:
        panel = app.query_one(DockerProxyPanel)
        panel.infra = infra
        await pilot.click("#proxy-route-add")
        await pilot.pause()
        select = app.screen.query_one("#template-field-service-uuid", Select)
        assert select.value is Select.NULL
        select.value = "backend-1"
        select.clear()
        assert select.value is Select.NULL
        form = app.screen.query_one("#template-setup-dialog")
        assert form is not None


def test_add_route_dialog_opens_with_optional_service_unselected():
    asyncio.run(_open_add_route_with_optional_service())


async def _route_buttons_are_separated():
    app = ProxyApp()
    async with app.run_test(size=(80, 24)) as pilot:
        await pilot.pause()
        add = app.query_one("#proxy-route-add", Button)
        remove = app.query_one("#proxy-route-remove", Button)
        assert remove.region.x >= add.region.right + 2


def test_route_action_buttons_have_spacing():
    asyncio.run(_route_buttons_are_separated())
