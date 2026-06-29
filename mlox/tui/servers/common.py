"""Shared TUI server setup form helpers."""

from __future__ import annotations

from typing import Any

from mlox.tui.template_forms import FormValues, TemplateFieldSpec, TemplateFormSpec


def native_fields() -> list[TemplateFieldSpec]:
    return [
        TemplateFieldSpec("host", "Host", placeholder="server.example.org"),
        TemplateFieldSpec(
            "port",
            "SSH port",
            kind="integer",
            default="22",
            min_value=1,
            max_value=65535,
        ),
        TemplateFieldSpec("user", "Login user", default="root"),
        TemplateFieldSpec("password", "Password", kind="password", required=False),
    ]


def native_params(values: FormValues, _infra: Any) -> dict[str, str]:
    return {
        "${MLOX_IP}": values.get("host", ""),
        "${MLOX_PORT}": values.get("port", "22"),
        "${MLOX_ROOT}": values.get("user", "root"),
        "${MLOX_ROOT_PW}": values.get("password", ""),
    }


def multipass_fields() -> list[TemplateFieldSpec]:
    return [
        TemplateFieldSpec("vm_name", "VM name", default="mlox-vm"),
        TemplateFieldSpec("cpus", "CPUs", kind="integer", default="2", min_value=1),
        TemplateFieldSpec("memory", "RAM", default="4G"),
        TemplateFieldSpec("disk", "Disk", default="20G"),
        TemplateFieldSpec("image", "Ubuntu image", default="24.04"),
        TemplateFieldSpec(
            "cloud_init",
            "Cloud-init path",
            required=False,
            help="Leave empty to use the bundled MLOX cloud-init file.",
        ),
        TemplateFieldSpec(
            "launch_timeout",
            "Launch timeout seconds",
            kind="integer",
            default="600",
            min_value=60,
        ),
    ]


def multipass_params(values: FormValues, _infra: Any) -> dict[str, str]:
    return {
        "${MULTIPASS_VM_NAME}": values.get("vm_name", ""),
        "${MULTIPASS_CPUS}": values.get("cpus", "2"),
        "${MULTIPASS_MEMORY}": values.get("memory", "4G"),
        "${MULTIPASS_DISK}": values.get("disk", "20G"),
        "${MULTIPASS_IMAGE}": values.get("image", "24.04"),
        "${MULTIPASS_CLOUD_INIT}": values.get("cloud_init", ""),
        "${MULTIPASS_LAUNCH_TIMEOUT}": values.get("launch_timeout", "600"),
    }


def k3s_controller_field(infra: Any) -> TemplateFieldSpec:
    options = [("Create new cluster", "")]
    controllers = (
        infra.list_kubernetes_controller()
        if infra and hasattr(infra, "list_kubernetes_controller")
        else []
    )
    for bundle in controllers:
        server = getattr(bundle, "server", None)
        uuid = str(getattr(server, "uuid", ""))
        if not uuid:
            continue
        name = getattr(bundle, "name", None) or getattr(server, "ip", "controller")
        options.append((str(name), uuid))
    return TemplateFieldSpec(
        "k3s_controller_uuid",
        "Kubernetes controller",
        kind="select",
        required=False,
        options=options,
        default="",
    )


def add_k3s_params(values: FormValues, infra: Any, params: dict[str, str]) -> dict[str, str]:
    controller_uuid = values.get("k3s_controller_uuid", "")
    controller = _find_controller(infra, controller_uuid)
    controller_url = ""
    controller_token = ""
    if controller:
        server = getattr(controller, "server", None)
        controller_url = f"https://{getattr(server, 'ip', '')}:6443"
        backend_status = server.get_backend_status()
        controller_token = str(backend_status.get("k3s.token", ""))
    params["${K3S_CONTROLLER_URL}"] = controller_url
    params["${K3S_CONTROLLER_TOKEN}"] = controller_token
    params["${K3S_CONTROLLER_UUID}"] = controller_uuid
    return params


def form_spec(
    *,
    title: str,
    description: str,
    fields: list[TemplateFieldSpec],
    materialize,
) -> TemplateFormSpec:
    return TemplateFormSpec(
        title=title,
        description=description,
        fields=fields,
        materialize=materialize,
        submit_label="Add Server",
    )


def _find_controller(infra: Any, controller_uuid: str):
    if not controller_uuid or not infra:
        return None
    for bundle in getattr(infra, "bundles", []) or []:
        server = getattr(bundle, "server", None)
        if str(getattr(server, "uuid", "")) == controller_uuid:
            return bundle
    return None
