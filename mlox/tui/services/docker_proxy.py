"""Live route controls for the standalone Docker proxy."""
import json

from textual import on
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Button, DataTable, Static

from mlox.tui.services.setup import _tls_secret_reference_options
from mlox.tui.template_forms import TemplateFieldSpec, TemplateFormSpec, TemplateSetupDialog


class DockerProxyPanel(Vertical):
    def __init__(self, infra, bundle, service):
        super().__init__()
        self.infra, self.bundle, self.service = infra, bundle, service
        self._hosts = []

    def compose(self) -> ComposeResult:
        yield Static('Public HTTPS routes. Existing backend services remain unchanged.')
        with Horizontal():
            yield Button('Add route', id='proxy-route-add', variant='primary')
            yield Button('Remove selected route', id='proxy-route-remove', variant='warning')
        table = DataTable(id='proxy-routes')
        table.cursor_type = 'row'
        table.add_columns('Hostname', 'Backend', 'Public TLS', 'Backend TLS')
        yield table
        yield Static('', id='proxy-status')

    def on_mount(self):
        self._refresh_routes()

    def _refresh_routes(self):
        table = self.query_one('#proxy-routes', DataTable)
        table.clear()
        self._hosts = sorted(self.service.routes)
        for host in self._hosts:
            route = self.service.routes[host]
            table.add_row(host, route['backend'], route.get('tls_mode', 'self-signed'),
                          'Unverified' if route.get('insecure_backend') else 'Verify')

    @on(Button.Pressed, '#proxy-route-add')
    def add_route(self):
        spec = TemplateFormSpec(
            title='Add proxy route', description='For a host-published endpoint, use https://host.docker.internal:PORT. A backend Host override may be needed.',
            fields=[
                TemplateFieldSpec('hostname', 'Public hostname', placeholder='notes.example.org'),
                TemplateFieldSpec('backend', 'Backend URL', placeholder='https://host.docker.internal:5230'),
                TemplateFieldSpec('service_uuid', 'Relayed mlox service', kind='select', required=False,
                                  options=[(f"{getattr(bundle, 'name', '')} / {item.name}", str(item.uuid))
                                           for bundle in getattr(self.infra, 'bundles', []) or []
                                           for item in getattr(bundle, 'services', []) or []
                                           if getattr(item, 'uuid', None) and item is not self.service],
                                  help='Optional: link this route to an installed service.'),
                TemplateFieldSpec('tls_mode', 'Public TLS', kind='select', default='self-signed', options=[('Self-signed', 'self-signed'), ("Let’s Encrypt", 'letsencrypt'), ('Managed certificate', 'managed')]),
                TemplateFieldSpec('tls_secret_ref', 'TLS secret (manager / name)', kind='select', visible_when=('tls_mode', 'managed'), options_loader=lambda: _tls_secret_reference_options(self.infra)),
                TemplateFieldSpec('insecure_backend', 'Backend certificate verification', kind='select', default='false', options=[('Verify', 'false'), ('Skip verification (self-signed backend)', 'true')]),
                TemplateFieldSpec('backend_host', 'Backend Host header override', required=False),
            ], materialize=lambda values, infra: values, submit_label='Add route',
        )
        self.app.push_screen(TemplateSetupDialog(spec), self._add_values)

    def _add_values(self, values):
        if values is None:
            return
        manager, secret = ('', '')
        if values['tls_mode'] == 'managed':
            manager, secret = json.loads(values['tls_secret_ref'])
        self._run(lambda ws: ws.add_proxy_route(name=self.service.name, hostname=values['hostname'], backend=values['backend'],
                  tls_mode=values['tls_mode'], insecure_backend=values['insecure_backend'] == 'true',
                  backend_host=values['backend_host'], tls_secret_manager_uuid=manager, tls_secret_name=secret,
                  service_uuid=values.get('service_uuid', '')))

    @on(Button.Pressed, '#proxy-route-remove')
    def remove_route(self):
        index = self.query_one('#proxy-routes', DataTable).cursor_row
        if index is None or not 0 <= index < len(self._hosts):
            self.notify('Select a route first.', severity='warning')
            return
        host = self._hosts[index]
        self._run(lambda ws: ws.remove_proxy_route(name=self.service.name, hostname=host))

    def _run(self, operation):
        workspace = getattr(self.app, 'workspace', None)
        if workspace is None:
            self.notify('Project workspace is unavailable.', severity='error')
            return
        for button in self.query(Button):
            button.disabled = True
        self.query_one('#proxy-status', Static).update('Applying route...')
        app = self.app

        def run():
            result = operation(workspace)
            app.call_from_thread(self._finish, result)

        app.run_worker(run, thread=True, exclusive=True, group=f'proxy-route-{id(self)}')

    def _finish(self, result):
        if not self.is_attached:
            return
        for button in self.query(Button):
            button.disabled = False
        self.query_one('#proxy-status', Static).update(result.message)
        workspace = getattr(self.app, 'workspace', None)
        infrastructure = getattr(workspace, 'infrastructure', None)
        if infrastructure is not None:
            current = infrastructure.get_service(self.service.name)
            if current is not None:
                self.service = current
        self._refresh_routes()
        if not result.success:
            self.notify(result.message, severity='error')


def settings(infra, bundle, service):
    return DockerProxyPanel(infra, bundle, service)
