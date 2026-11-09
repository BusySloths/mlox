"""Application operations for the standalone Docker reverse proxy."""
from mlox.application.result import OperationResult
from mlox.service import AbstractProxyService


def _get_proxy(project, name):
    service = project.infrastructure.get_service(name)
    if not isinstance(service, AbstractProxyService):
        raise ValueError('Docker proxy service not found.')
    bundle = project.infrastructure.get_bundle_by_service(service)
    if not bundle:
        raise ValueError('The proxy is not attached to a server.')
    if service.state == 'un-initialized':
        raise ValueError('Set up the proxy before managing routes.')
    return service, bundle


def list_routes(project, *, name):
    try:
        service, _ = _get_proxy(project, name)
        return OperationResult(True, 0, 'Proxy routes retrieved.', {'routes': service.list_routes()})
    except ValueError as exc:
        return OperationResult(False, 1, str(exc))


def add_route(project, *, name, hostname, backend="", tls_mode='self-signed', insecure_backend=False, backend_host='', tls_secret_manager_uuid='', tls_secret_name='', service_uuid=''):
    try:
        service, bundle = _get_proxy(project, name)
        app = project.infrastructure.get_service_by_uuid(service_uuid) if service_uuid else None
        if service_uuid and app is None:
            raise ValueError('The selected relayed service no longer exists.')
        if not backend and app is not None:
            app_bundle = project.infrastructure.get_bundle_by_service(app)
            getter = getattr(app, 'get_proxy_endpoint', None)
            if app_bundle is None or not callable(getter):
                raise ValueError('The selected app does not provide a proxy endpoint; supply a backend URL.')
            endpoint = getter(
                app_host=str(getattr(app_bundle.server, 'ip', '') or ''),
                proxy_host=str(getattr(bundle.server, 'ip', '') or ''),
            )
            if not isinstance(endpoint, dict) or not endpoint.get('url'):
                raise ValueError('The selected app has no proxy endpoint; supply a backend URL.')
            backend = str(endpoint['url'])
            backend_host = backend_host or str(endpoint.get('host_header', ''))
        if not backend:
            raise ValueError('Select an app or supply a backend URL.')
        with bundle.server.get_server_connection() as conn:
            service.add_route(conn, hostname=hostname, backend=backend, tls_mode=tls_mode,
                              insecure_backend=insecure_backend, backend_host=backend_host,
                              tls_secret_manager_uuid=tls_secret_manager_uuid,
                              tls_secret_name=tls_secret_name, service_uuid=service_uuid)
        return OperationResult(True, 0, f'Added proxy route for {hostname}.', {'routes': service.list_routes()})
    except Exception as exc:
        return OperationResult(False, 1, f'Could not add proxy route: {exc}')


def remove_route(project, *, name, hostname):
    try:
        service, bundle = _get_proxy(project, name)
        with bundle.server.get_server_connection() as conn:
            service.remove_route(conn, hostname=hostname)
        return OperationResult(True, 0, f'Removed proxy route for {hostname}.', {'routes': service.list_routes()})
    except Exception as exc:
        return OperationResult(False, 1, f'Could not remove proxy route: {exc}')
