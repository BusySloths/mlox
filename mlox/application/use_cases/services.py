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


def service_has_health(service: object | None) -> bool:
    """Return whether a service advertises live health checks."""

    if not service:
        return False
    if ServiceCapability.HEALTH.value in _service_capability_names(service):
        return callable(getattr(service, "get_health", None))
    return False


def service_can_restart(service: object | None) -> bool:
    """Return whether a service provides a meaningful restart/repair action."""

    if not service or getattr(service, "state", "unknown") == "un-initialized":
        return False
    if not callable(getattr(service, "restart", None)):
        return False
    if _service_has_compose_restart(service):
        return True
    if not isinstance(service, AbstractService):
        return True
    return getattr(type(service), "restart", None) is not AbstractService.restart


def check_service_health(project: WorkspaceState, *, name: str) -> OperationResult:
    """Run a service health check and persist the service state."""

    infra = project.infrastructure
    service = infra.get_service(name)
    if not service:
        return OperationResult(False, 54, "Service not found in infrastructure.")
    if not service_has_health(service):
        return OperationResult(
            False,
            55,
            "Selected service does not provide health checks.",
        )
    bundle = infra.get_bundle_by_service(service)
    if not bundle:
        return OperationResult(False, 56, "Could not find server bundle for service.")

    try:
        with bundle.server.get_server_connection() as conn:
            health = service.get_health(conn)
    except Exception as exc:
        return OperationResult(False, 57, f"Failed to check service health: {exc}")

    if not isinstance(health, dict):
        return OperationResult(
            False,
            58,
            "Selected service returned invalid health data.",
        )

    _update_service_state_from_health(service, health)
    status = str(health.get("status") or getattr(service, "state", "unknown"))
    return OperationResult(
        True,
        0,
        f"Service health checked: {status}.",
        {"service": service, "health": health},
    )


def check_service_health_in_workspace(workspace, service) -> OperationResult:
    """Check service health through an open workspace adapter."""

    if not workspace:
        return OperationResult(False, 59, "Project workspace is unavailable.")
    if not service:
        return OperationResult(False, 60, "No service selected.")
    check_health = getattr(workspace, "check_service_health", None)
    if not callable(check_health):
        return OperationResult(
            False,
            61,
            "Project workspace cannot check service health.",
        )
    try:
        return check_health(name=str(getattr(service, "name", "")))
    except Exception as exc:
        return OperationResult(False, 62, f"Failed to check service health: {exc}")


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
                    "labels": _service_log_labels(service),
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
    if getattr(service, "state", "unknown") != "un-initialized":
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


def restart_service(project: WorkspaceState, *, name: str) -> OperationResult:
    """Restart or repair an initialized service using its current configuration."""

    infra = project.infrastructure
    service = infra.get_service(name)
    if not service:
        return OperationResult(False, 8, "Service not found in infrastructure.")
    if getattr(service, "state", "unknown") == "un-initialized":
        return OperationResult(False, 14, "Set up the service before restarting it.")
    bundle = infra.get_bundle_by_service(service)
    if not bundle:
        return OperationResult(False, 10, "Could not find server bundle for service.")
    if not service_can_restart(service):
        return OperationResult(False, 15, "Selected service cannot be restarted.")
    with bundle.server.get_server_connection() as conn:
        service.restart(conn)
    return OperationResult(
        True,
        0,
        f"Service {name} restarted.",
        {"service": service},
    )


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


def _update_service_state_from_health(service: object, health: Dict[str, Any]) -> None:
    state = str(health.get("state") or health.get("status") or "").strip()
    if state not in {
        "un-initialized",
        "running",
        "stopped",
        "starting",
        "terminating",
        "failed",
        "error",
        "unknown",
    }:
        if health.get("healthy") is True:
            state = "running"
        elif health.get("healthy") is False:
            state = "unknown"
    if state:
        try:
            setattr(service, "state", state)
        except Exception:
            pass


def _service_capability_names(service: object) -> set[str]:
    return {
        capability.value if hasattr(capability, "value") else str(capability)
        for capability in getattr(service, "capabilities", set()) or set()
    }


def _service_has_compose_restart(service: object) -> bool:
    return bool(
        getattr(service, "compose_service_names", None)
        and callable(getattr(getattr(service, "exec", None), "docker_restart", None))
    )


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
        labels = _service_log_labels(service)
        if not labels:
            return OperationResult(
                False, 9, "No log labels configured for this service."
            )
        chosen_label = labels[0]
    bundle = infra.get_bundle_by_service(service)
    if not bundle:
        return OperationResult(False, 10, "Could not find server bundle for service.")
    with bundle.server.get_server_connection() as conn:
        log_tail = getattr(service, "service_log_tail", None)
        if callable(log_tail):
            logs = log_tail(conn, label=chosen_label, tail=tail)
        else:
            logs = service.compose_service_log_tail(conn, label=chosen_label, tail=tail)
    return OperationResult(True, 0, "Fetched service logs.", {"logs": logs})


def _service_log_labels(service: object) -> List[str]:
    labels = getattr(service, "log_labels", None)
    if callable(labels):
        return list(labels())
    return list((getattr(service, "compose_service_names", {}) or {}).keys())


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


def resolve_service_template_setup(
    infra,
    bundle,
    config,
    *,
    ui: str = "tui",
    handler: str = "setup",
) -> OperationResult:
    """Resolve a service-template setup handler for UI adapters."""

    if not config:
        return OperationResult(False, 31, "No service template selected.")
    if not bundle:
        return OperationResult(False, 32, "No target bundle selected.")

    callable_setup = config.get_ui_handler(ui, handler)
    if not callable(callable_setup):
        return OperationResult(
            False,
            33,
            "Selected service template does not provide a TUI setup form.",
        )

    try:
        setup = callable_setup(infra, bundle, config)
    except TypeError:
        setup = callable_setup(infra, bundle)
    except Exception as exc:
        return OperationResult(False, 34, f"Failed to load service setup form: {exc}")

    if setup is None:
        return OperationResult(
            False,
            35,
            "Selected service template is missing required setup data.",
        )
    return OperationResult(True, 0, "Loaded service setup form.", {"setup": setup})


def materialize_service_template_params(setup, values, infra) -> OperationResult:
    """Convert setup form values to service template placeholder parameters."""

    if not setup:
        return OperationResult(False, 36, "No service setup form is available.")
    try:
        params = setup.params(values, infra)
    except Exception as exc:
        return OperationResult(False, 37, f"Failed to prepare service parameters: {exc}")
    return OperationResult(
        True,
        0,
        "Prepared service parameters.",
        {"params": params},
    )


def add_service_from_template(
    workspace,
    bundle,
    config,
    params: Dict[str, str],
) -> OperationResult:
    """Add a service template to a bundle without setting it up."""

    if not workspace:
        return OperationResult(False, 38, "Project workspace is unavailable.")
    server = getattr(bundle, "server", None)
    server_ip = getattr(server, "ip", "")
    if not bundle or not server or not server_ip:
        return OperationResult(False, 39, "No target bundle selected.")
    add_from_config = getattr(workspace, "add_service_from_config", None)
    if not callable(add_from_config):
        return OperationResult(
            False,
            40,
            "Project workspace cannot add service templates.",
        )
    try:
        return add_from_config(config, server_ip=server_ip, params=params or {})
    except Exception as exc:
        return OperationResult(False, 41, f"Failed to add service: {exc}")


def setup_service_in_workspace(workspace, service) -> OperationResult:
    """Set up one service through an open workspace adapter."""

    if not workspace:
        return OperationResult(False, 42, "Project workspace is unavailable.")
    if not service:
        return OperationResult(False, 43, "No service selected.")
    setup = getattr(workspace, "setup_service", None)
    if not callable(setup):
        return OperationResult(False, 44, "Project workspace cannot set up services.")
    try:
        return setup(name=str(getattr(service, "name", "")))
    except Exception as exc:
        return OperationResult(False, 45, f"Failed to set up service: {exc}")


def restart_service_in_workspace(workspace, service) -> OperationResult:
    """Restart or repair one service through an open workspace adapter."""

    if not workspace:
        return OperationResult(False, 63, "Project workspace is unavailable.")
    if not service:
        return OperationResult(False, 64, "No service selected.")
    restart = getattr(workspace, "restart_service", None)
    if not callable(restart):
        return OperationResult(False, 65, "Project workspace cannot restart services.")
    try:
        return restart(name=str(getattr(service, "name", "")))
    except Exception as exc:
        return OperationResult(False, 66, f"Failed to restart service: {exc}")


def teardown_service_in_workspace(workspace, service) -> OperationResult:
    """Tear down and remove one service through an open workspace adapter."""

    if not workspace:
        return OperationResult(False, 46, "Project workspace is unavailable.")
    if not service:
        return OperationResult(False, 47, "No service selected.")
    teardown = getattr(workspace, "teardown_service", None)
    if not callable(teardown):
        return OperationResult(False, 48, "Project workspace cannot teardown services.")
    try:
        return teardown(name=str(getattr(service, "name", "")))
    except Exception as exc:
        return OperationResult(False, 49, f"Failed to teardown service: {exc}")


def rename_service_in_workspace(workspace, service, new_name: str) -> OperationResult:
    """Rename one service through an open workspace adapter."""

    if not workspace:
        return OperationResult(False, 50, "Project workspace is unavailable.")
    if not service:
        return OperationResult(False, 51, "No service selected.")
    rename = getattr(workspace, "rename_service", None)
    if not callable(rename):
        return OperationResult(False, 52, "Project workspace cannot rename services.")
    try:
        return rename(
            name=str(getattr(service, "name", "")),
            new_name=new_name,
        )
    except Exception as exc:
        return OperationResult(False, 53, f"Failed to rename service: {exc}")


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
