"""Application operations for the standalone Docker reverse proxy."""
from mlox.application.result import OperationResult
from mlox.services.docker_proxy.docker import DockerProxyService


def _get_proxy(project, name):
    service = project.infrastructure.get_service(name)
    if not isinstance(service, DockerProxyService):
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
        return OperationResult(True, 0, 'Proxy routes retrieved.', {'routes': service.routes})
    except ValueError as exc:
        return OperationResult(False, 1, str(exc))


def add_route(project, *, name, hostname, backend, tls_mode='self-signed', insecure_backend=False, backend_host='', tls_secret_manager_uuid='', tls_secret_name=''):
    try:
        service, bundle = _get_proxy(project, name)
        with bundle.server.get_server_connection() as conn:
            service.add_route(conn, hostname=hostname, backend=backend, tls_mode=tls_mode,
                              insecure_backend=insecure_backend, backend_host=backend_host,
                              tls_secret_manager_uuid=tls_secret_manager_uuid,
                              tls_secret_name=tls_secret_name)
        return OperationResult(True, 0, f'Added proxy route for {hostname}.', {'routes': service.routes})
    except Exception as exc:
        return OperationResult(False, 1, f'Could not add proxy route: {exc}')


def remove_route(project, *, name, hostname):
    try:
        service, bundle = _get_proxy(project, name)
        with bundle.server.get_server_connection() as conn:
            service.remove_route(conn, hostname=hostname)
        return OperationResult(True, 0, f'Removed proxy route for {hostname}.', {'routes': service.routes})
    except Exception as exc:
        return OperationResult(False, 1, f'Could not remove proxy route: {exc}')
