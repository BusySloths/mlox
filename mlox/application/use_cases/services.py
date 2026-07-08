from __future__ import annotations

import webbrowser
from typing import Any, Dict, List, Optional

from mlox.application.result import OperationResult
from mlox.config import get_stacks_path, load_all_service_configs
from mlox.project.state import WorkspaceState
from mlox.service import AbstractService, AbstractWebUIService, ServiceCapability
from mlox.utils import auto_map_ports, generate_pw, generate_username


def service_has_web_ui(service: object | None) -> bool:
    """Return whether a service advertises a browser-facing UI capability."""

    if isinstance(service, AbstractWebUIService):
        return True
    capabilities = getattr(service, "capabilities", set()) if service else set()
    for capability in capabilities or []:
        value = capability.value if hasattr(capability, "value") else capability
        if (
            str(value).strip().lower().replace("-", "_")
            == ServiceCapability.WEB_UI.value
        ):
            return True
    return callable(getattr(service, "get_web_ui_address", None))


def get_service_web_ui_address(service: object | None) -> OperationResult:
    """Resolve the browser URL for a web UI-capable service."""

    if service is None:
        return OperationResult(False, 20, "Service not found.")
    if not service_has_web_ui(service):
        return OperationResult(False, 21, "Selected service does not provide a web UI.")

    getter = getattr(service, "get_web_ui_address", None)
    if not callable(getter):
        return OperationResult(
            False,
            22,
            "Selected service cannot resolve a web UI address.",
        )

    try:
        url = str(getter()).strip()
    except Exception as exc:
        return OperationResult(False, 23, f"Failed to resolve service web UI: {exc}")

    if not url:
        return OperationResult(
            False,
            24,
            "Service web UI address is not available yet. Set up the service first.",
        )

    return OperationResult(True, 0, "Service web UI address resolved.", {"url": url})


def list_service_web_ui_login_fields(service: object | None) -> OperationResult:
    """Return browser-login fields advertised by a web UI-capable service."""

    if service is None:
        return OperationResult(False, 20, "Service not found.")
    if not service_has_web_ui(service):
        return OperationResult(False, 21, "Selected service does not provide a web UI.")

    fields = [
        str(field).strip()
        for field in getattr(service, "web_ui_login_fields", ()) or ()
        if str(field).strip()
    ]
    return OperationResult(
        True,
        0,
        "Service web UI login fields resolved.",
        {"fields": fields},
    )


def get_service_web_ui_login_value(
    service: object | None,
    field: str,
    *,
    bundle: object | None = None,
) -> OperationResult:
    """Resolve one browser-login credential value for a web UI-capable service."""

    if service is None:
        return OperationResult(False, 20, "Service not found.")
    if not service_has_web_ui(service):
        return OperationResult(False, 21, "Selected service does not provide a web UI.")

    field = field.strip().lower()
    if not field:
        return OperationResult(False, 26, "Login field is required.")

    getter = getattr(service, "get_web_ui_login", None)
    if not callable(getter):
        return OperationResult(
            False,
            27,
            "Selected service does not provide web UI login details.",
        )

    try:
        login = getter(bundle=bundle)
    except TypeError:
        login = getter()
    except Exception as exc:
        return OperationResult(False, 28, f"Failed to resolve web UI login: {exc}")

    if not isinstance(login, dict):
        return OperationResult(
            False,
            29,
            "Selected service returned invalid web UI login details.",
        )

    value = str(login.get(field, "") or "")
    if not value:
        return OperationResult(
            False,
            30,
            f"Web UI {field} is not available yet.",
        )

    return OperationResult(
        True,
        0,
        f"Service web UI {field} resolved.",
        {"field": field, "value": value},
    )


def open_service_web_ui(
    service: object | None,
    *,
    opener=None,
) -> OperationResult:
    """Open the browser URL for a web UI-capable service."""

    result = get_service_web_ui_address(service)
    if not result.success:
        return result

    url = result.data["url"] if result.data else ""
    open_url = opener or webbrowser.open
    try:
        opened = open_url(url)
    except Exception as exc:
        return OperationResult(False, 25, f"Failed to open service web UI: {exc}")

    if opened is False:
        return OperationResult(False, 25, "Failed to open service web UI.")
    return OperationResult(True, 0, f"Opened service web UI: {url}", {"url": url})


def list_services(project: WorkspaceState) -> OperationResult:
    payload: List[Dict[str, Any]] = []
    for bundle in project.infrastructure.bundles:
        for service in bundle.services:
            payload.append(
                {
                    "name": service.name,
                    "service_config_id": getattr(
                        service, "service_config_id", "unknown"
                    ),
                    "server_ip": bundle.server.ip,
                    "state": getattr(service, "state", "unknown"),
                    "labels": list(
                        getattr(service, "compose_service_names", {}).keys()
                    ),
                    "ports": [
                        f"{name}:{port}"
                        for name, port in (
                            getattr(service, "service_ports", {}) or {}
                        ).items()
                    ],
                    "urls": [
                        f"{name}: {url}"
                        for name, url in (
                            getattr(service, "service_urls", {}) or {}
                        ).items()
                    ],
                }
            )
    message = "No services found." if not payload else "Services retrieved successfully."
    return OperationResult(True, 0, message, {"services": payload})


def add_service(
    project: WorkspaceState,
    load_service_config,
    *,
    server_ip: str,
    template_id: str,
    params: Optional[Dict[str, str]] = None,
    service: AbstractService | None = None,
) -> OperationResult:
    config = load_service_config(template_id)
    if not config:
        return OperationResult(False, 6, "Service template not found.")
    infra = project.infrastructure
    bundle = infra.get_bundle_by_ip(server_ip)
    if not bundle or not bundle.server or not bundle.server.mlox_user:
        return OperationResult(False, 7, "Failed to add service to server.")

    values: Dict[str, Any] = dict(params or {})
    if service is None:
        values.update(
            {
                "${MLOX_STACKS_PATH}": get_stacks_path(),
                "${MLOX_USER}": bundle.server.mlox_user.name,
                "${MLOX_USER_HOME}": bundle.server.mlox_user.home,
                "${MLOX_AUTO_USER}": generate_username(),
                "${MLOX_AUTO_PW}": generate_pw(),
                "${MLOX_AUTO_API_KEY}": generate_pw(),
                "${MLOX_SERVER_IP}": bundle.server.ip,
                "${MLOX_SERVER_UUID}": bundle.server.uuid,
            }
        )
        ports = dict(config.ports)
        restricted = ports.pop("restricted", [])
        used_ports = list(restricted) if isinstance(restricted, list) else []
        for existing in bundle.services:
            used_ports.extend(existing.service_ports.values())
        values.update(
            {
                f"${{MLOX_AUTO_PORT_{name.upper()}}}": str(port)
                for name, port in auto_map_ports(used_ports, ports).items()
            }
        )
        service = config.instantiate_service(params=values)
    if not service:
        return OperationResult(False, 7, "Failed to instantiate service.")

    existing_names = infra.list_service_names()
    base_name = service.name
    counter = 0
    while service.name in existing_names:
        service.name = f"{base_name}_{counter}"
        counter += 1
    infra.configs[config.id] = config
    service.set_task_executor(bundle.server.create_new_task_executor())
    service.bind_service_lookup(infra)
    bundle.services.append(service)
    return OperationResult(
        True,
        0,
        f"Added service {service.name} to {server_ip}.",
        {"service": service},
    )


def setup_service(project: WorkspaceState, *, name: str) -> OperationResult:
    infra = project.infrastructure
    service = infra.get_service(name)
    if not service:
        return OperationResult(False, 8, "Service not found in infrastructure.")
    bundle = infra.get_bundle_by_service(service)
    if not bundle:
        return OperationResult(False, 10, "Could not find server bundle for service.")
    with bundle.server.get_server_connection() as conn:
        service.setup(conn)
        service.spin_up(conn)
    return OperationResult(True, 0, f"Service {name} set up.", {"service": service})


def teardown_service(project: WorkspaceState, *, name: str) -> OperationResult:
    infra = project.infrastructure
    service = infra.get_service(name)
    if not service:
        return OperationResult(False, 8, "Service not found in infrastructure.")
    bundle = infra.get_bundle_by_service(service)
    if not bundle:
        return OperationResult(False, 10, "Could not find server bundle for service.")
    with bundle.server.get_server_connection() as conn:
        service.spin_down(conn)
        service.teardown(conn)
    bundle.services.remove(service)
    service.clear_service_lookup()
    return OperationResult(True, 0, f"Service {name} removed.", {"service": service})


def start_service(project: WorkspaceState, *, name: str) -> OperationResult:
    infra = project.infrastructure
    service = infra.get_service(name)
    if not service:
        return OperationResult(False, 8, "Service not found in infrastructure.")
    bundle = infra.get_bundle_by_service(service)
    if not bundle:
        return OperationResult(False, 10, "Could not find server bundle for service.")
    with bundle.server.get_server_connection() as conn:
        service.spin_up(conn)
    return OperationResult(True, 0, f"Service {name} started.", {"service": service})


def stop_service(project: WorkspaceState, *, name: str) -> OperationResult:
    infra = project.infrastructure
    service = infra.get_service(name)
    if not service:
        return OperationResult(False, 8, "Service not found in infrastructure.")
    bundle = infra.get_bundle_by_service(service)
    if not bundle:
        return OperationResult(False, 10, "Could not find server bundle for service.")
    with bundle.server.get_server_connection() as conn:
        service.spin_down(conn)
    return OperationResult(True, 0, f"Service {name} stopped.", {"service": service})


def rename_service(project: WorkspaceState, *, name: str, new_name: str) -> OperationResult:
    infra = project.infrastructure
    service = infra.get_service(name)
    if not service:
        return OperationResult(False, 8, "Service not found in infrastructure.")
    new_name = new_name.strip()
    if not new_name:
        return OperationResult(False, 11, "Service name must not be empty.")
    if new_name != name and new_name in infra.list_service_names():
        return OperationResult(False, 11, "Service name must be unique.")
    service.name = new_name
    return OperationResult(
        True,
        0,
        f"Service {name} renamed to {new_name}.",
        {"service": service},
    )


def service_logs(
    project: WorkspaceState,
    *,
    name: str,
    label: Optional[str] = None,
    tail: int = 200,
) -> OperationResult:
    infra = project.infrastructure
    service = infra.get_service(name)
    if not service:
        return OperationResult(False, 8, "Service not found in infrastructure.")
    chosen_label = label
    if chosen_label is None:
        compose_names = getattr(service, "compose_service_names", {})
        if not compose_names:
            return OperationResult(
                False, 9, "No compose service labels configured for this service."
            )
        chosen_label = next(iter(compose_names))
    bundle = infra.get_bundle_by_service(service)
    if not bundle:
        return OperationResult(False, 10, "Could not find server bundle for service.")
    with bundle.server.get_server_connection() as conn:
        logs = service.compose_service_log_tail(conn, label=chosen_label, tail=tail)
    return OperationResult(True, 0, "Fetched service logs.", {"logs": logs})


def list_service_configs(list_configs) -> OperationResult:
    payload = [{"id": cfg.id, "path": cfg.path} for cfg in list_configs()]
    message = "No service configs found." if not payload else "Service configs retrieved."
    return OperationResult(True, 0, message, {"configs": payload})


def browse_service_templates(
    *,
    backends: set[str] | None = None,
    list_configs=None,
) -> OperationResult:
    """Return service template config objects for UI browsing."""

    list_configs = list_configs or load_all_service_configs
    configs = list(list_configs())
    if backends:
        configs = [
            config
            for config in configs
            if backends & config.backend_capabilities()
        ]
    message = "No service templates found." if not configs else "Service templates loaded."
    return OperationResult(True, 0, message, {"configs": configs})


def build_service_ui_widget(
    infra,
    bundle,
    service,
    *,
    ui: str = "tui",
    handler: str = "settings",
) -> OperationResult:
    """Resolve and invoke a service UI handler through the infrastructure config."""

    if not infra or not bundle:
        return OperationResult(
            False,
            16,
            "Service UI is unavailable because the infrastructure is not loaded.",
        )

    get_service_config = getattr(infra, "get_service_config", None)
    config = get_service_config(service) if callable(get_service_config) else None
    if not config:
        return OperationResult(
            False,
            17,
            "Unable to resolve a configuration for the selected service.",
        )

    callable_settings = config.get_ui_handler(ui, handler)
    if not callable_settings:
        return OperationResult(
            False,
            18,
            "Selected service does not provide a TUI view.",
        )

    try:
        widget = callable_settings(infra, bundle, service)
    except Exception as exc:
        return OperationResult(False, 19, f"Failed to load service UI: {exc}")

    return OperationResult(True, 0, "Loaded service UI.", {"widget": widget})
