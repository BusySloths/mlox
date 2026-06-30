"""Application use-cases for project secret managers."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from mlox.application.result import OperationResult


def describe_secret_managers(workspace) -> OperationResult:
    """Return non-blocking metadata for every project secret manager."""

    if not workspace:
        return OperationResult(False, 1, "Project workspace is unavailable.")

    list_managers = getattr(workspace, "list_secret_managers", None)
    if not callable(list_managers):
        return OperationResult(
            False,
            2,
            "Project workspace cannot list secret managers.",
        )

    try:
        descriptors = list_managers()
    except Exception as exc:
        return OperationResult(False, 3, f"Could not list secret managers: {exc}")

    infra = getattr(workspace, "infrastructure", None)
    managers = [_manager_metadata(item, infra) for item in descriptors]
    return OperationResult(
        True,
        0,
        "Secret managers loaded.",
        {
            "managers": managers,
            "active_manager_id": _active_manager_id(managers),
        },
    )


def list_secret_names(workspace, manager_id: str) -> OperationResult:
    """List redacted secret keys for one selected secret manager."""

    descriptor_result = _resolve_secret_manager(workspace, manager_id)
    if not descriptor_result.success:
        return descriptor_result

    descriptor = descriptor_result.data["descriptor"]
    manager = descriptor.manager
    if manager is None:
        return OperationResult(False, 6, "Secret manager is unavailable.")

    try:
        listed = manager.list_secrets(keys_only=True)
    except Exception as exc:
        infra = getattr(workspace, "infrastructure", None)
        return OperationResult(
            False,
            7,
            f"Could not list secrets for '{descriptor.name}': {exc}",
            {"manager": _manager_metadata(descriptor, infra)},
        )

    secret_names = sorted(str(name) for name in (listed or {}).keys())
    secrets = [{"name": name, "value": "hidden"} for name in secret_names]
    infra = getattr(workspace, "infrastructure", None)
    return OperationResult(
        True,
        0,
        f"Secret keys loaded for '{descriptor.name}'.",
        {
            "manager": _manager_metadata(descriptor, infra),
            "secrets": secrets,
        },
    )


def reveal_secret(workspace, manager_id: str, name: str) -> OperationResult:
    """Load one secret value from the selected project secret manager."""

    secret_name = str(name).strip()
    if not secret_name:
        return OperationResult(False, 8, "No secret selected.")

    descriptor_result = _resolve_secret_manager(workspace, manager_id)
    if not descriptor_result.success:
        return descriptor_result

    descriptor = descriptor_result.data["descriptor"]
    manager = descriptor.manager
    if manager is None:
        return OperationResult(False, 9, "Secret manager is unavailable.")

    try:
        value = manager.load_secret(secret_name)
    except Exception as exc:
        return OperationResult(
            False,
            10,
            f"Could not load secret '{secret_name}': {exc}",
            {
                "manager": _manager_metadata(
                    descriptor,
                    getattr(workspace, "infrastructure", None),
                ),
                "name": secret_name,
            },
        )

    if value is None:
        return OperationResult(
            False,
            11,
            f"Secret '{secret_name}' was not found.",
            {
                "manager": _manager_metadata(
                    descriptor,
                    getattr(workspace, "infrastructure", None),
                ),
                "name": secret_name,
            },
        )

    return OperationResult(
        True,
        0,
        f"Loaded secret '{secret_name}'.",
        {
            "manager": _manager_metadata(
                descriptor,
                getattr(workspace, "infrastructure", None),
            ),
            "name": secret_name,
            "value": deepcopy(value),
        },
    )


def save_secret(workspace, manager_id: str, name: str, value: Any) -> OperationResult:
    """Create or update one secret in the selected project secret manager."""

    secret_name = str(name).strip()
    if not secret_name:
        return OperationResult(False, 12, "Secret key must not be empty.")

    descriptor_result = _resolve_secret_manager(workspace, manager_id)
    if not descriptor_result.success:
        return descriptor_result

    descriptor = descriptor_result.data["descriptor"]
    manager = descriptor.manager
    if manager is None:
        return OperationResult(False, 13, "Secret manager is unavailable.")

    try:
        manager.save_secret(secret_name, value)
    except Exception as exc:
        return OperationResult(
            False,
            14,
            f"Could not save secret '{secret_name}': {exc}",
            {
                "manager": _manager_metadata(
                    descriptor,
                    getattr(workspace, "infrastructure", None),
                ),
                "name": secret_name,
            },
        )

    return OperationResult(
        True,
        0,
        f"Saved secret '{secret_name}'.",
        {
            "manager": _manager_metadata(
                descriptor,
                getattr(workspace, "infrastructure", None),
            ),
            "name": secret_name,
            "value": deepcopy(value),
        },
    )


def activate_secret_manager(workspace, manager_id: str) -> OperationResult:
    """Make one available secret manager the active project secret manager."""

    selected_id = str(manager_id).strip()
    if not selected_id:
        return OperationResult(False, 15, "No secret manager selected.")
    if not workspace:
        return OperationResult(False, 1, "Project workspace is unavailable.")

    if selected_id == "embedded":
        use_embedded = getattr(workspace, "use_embedded_secret_manager", None)
        if not callable(use_embedded):
            return OperationResult(
                False,
                16,
                "Embedded secret manager is unavailable.",
            )
        return use_embedded()

    set_manager = getattr(workspace, "set_secret_manager", None)
    if not callable(set_manager):
        return OperationResult(False, 17, "Project workspace cannot switch managers.")
    return set_manager(selected_id)


def _resolve_secret_manager(workspace, manager_id: str) -> OperationResult:
    selected_id = str(manager_id).strip()
    if not selected_id:
        return OperationResult(False, 4, "No secret manager selected.")
    if not workspace:
        return OperationResult(False, 1, "Project workspace is unavailable.")

    probe = getattr(workspace, "probe_secret_manager", None)
    if callable(probe):
        try:
            descriptor = probe(selected_id)
        except Exception as exc:
            return OperationResult(False, 5, f"Secret manager not found: {exc}")
        return OperationResult(
            True,
            0,
            "Secret manager resolved.",
            {"descriptor": descriptor},
        )

    manager = getattr(workspace, "secrets", None)
    if selected_id == "embedded" and manager is not None:
        return OperationResult(
            True,
            0,
            "Secret manager resolved.",
            {"descriptor": _LegacySecretManagerDescriptor(workspace, manager)},
        )
    return OperationResult(False, 5, "Secret manager not found.")


def _manager_metadata(descriptor, infra=None) -> dict[str, Any]:
    available = getattr(descriptor, "is_available", None)
    return {
        "id": str(getattr(descriptor, "id", "")),
        "name": str(getattr(descriptor, "name", "Unknown")),
        "kind": str(getattr(descriptor, "kind", "unknown")),
        "service_uuid": getattr(descriptor, "service_uuid", None),
        "location": _manager_location(descriptor, infra),
        "is_active": bool(getattr(descriptor, "is_active", False)),
        "is_available": available if isinstance(available, bool) else None,
        "status": _manager_status(available),
        "class": _manager_class(descriptor),
        "supports_keyfile_export": bool(
            getattr(descriptor, "supports_keyfile_export", False)
        ),
    }


def _manager_location(descriptor, infra=None) -> dict[str, str]:
    service = getattr(descriptor, "service", None)
    if service is None:
        return {
            "bundle": "Project",
            "backend": "embedded",
            "service": "",
        }

    bundle = _service_bundle(infra, service)
    server = getattr(bundle, "server", None) if bundle is not None else None
    return {
        "bundle": str(getattr(bundle, "name", "-")) if bundle is not None else "-",
        "backend": _backend_label(server),
        "service": str(getattr(service, "name", "-")),
    }


def _service_bundle(infra, service):
    for bundle in getattr(infra, "bundles", []) or []:
        if service in (getattr(bundle, "services", []) or []):
            return bundle
    return getattr(service, "bundle", None)


def _backend_label(server) -> str:
    backends = getattr(server, "backend", []) if server is not None else []
    if isinstance(backends, str):
        backends = [backends]
    label = ", ".join(str(backend) for backend in backends if str(backend).strip())
    return label or "-"


def _manager_class(descriptor) -> str:
    manager = getattr(descriptor, "manager", None)
    if manager is not None:
        return manager.__class__.__name__
    service = getattr(descriptor, "service", None)
    if service is not None:
        return service.__class__.__name__
    return "-"


def _manager_status(is_available: bool | None) -> str:
    if is_available is True:
        return "available"
    if is_available is False:
        return "unavailable"
    return "not checked"


def _active_manager_id(managers: list[dict[str, Any]]) -> str | None:
    for manager in managers:
        if manager["is_active"]:
            return str(manager["id"])
    return managers[0]["id"] if managers else None


class _LegacySecretManagerDescriptor:
    """Adapter for older tests/fakes that expose only ``workspace.secrets``."""

    id = "embedded"
    kind = "embedded"
    service_uuid = None
    is_active = True
    service = None

    def __init__(self, workspace, manager) -> None:
        self.name = str(
            getattr(workspace, "active_secret_manager_name", "Secret Manager")
        )
        self.manager = manager
        try:
            self.is_available = manager.is_working()
        except Exception:
            self.is_available = False
        self.supports_keyfile_export = bool(
            getattr(manager, "supports_keyfile_export", False)
        )
