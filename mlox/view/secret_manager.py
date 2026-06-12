"""Streamlit page for selecting and using the project secret manager."""

from collections.abc import Callable
from typing import cast

import streamlit as st

from mlox.project import ProjectWorkspace
from mlox.project.secrets import SecretManagerDescriptor
from mlox.secret_manager import get_encrypted_access_keyfile
from mlox.utils import generate_pw
from mlox.view.services.common import render_secret_manager_settings


APPLICATION_PERIOD_OPTIONS = {
    "1 hour": "1h",
    "8 hours": "8h",
    "24 hours": "24h",
    "7 days": "168h",
    "30 days": "720h",
    "90 days": "2160h",
}


def _probe_cache(
    workspace: ProjectWorkspace,
) -> dict[str, SecretManagerDescriptor]:
    namespace = str(workspace.path)
    if st.session_state.get("secret_manager_cache_project") != namespace:
        st.session_state.secret_manager_cache_project = namespace
        st.session_state.secret_manager_probe_cache = {}
    return cast(
        dict[str, SecretManagerDescriptor],
        st.session_state.setdefault("secret_manager_probe_cache", {}),
    )


def _manager_label(descriptor: SecretManagerDescriptor) -> str:
    active = "Active · " if descriptor.is_active else ""
    return f"{active}{descriptor.name}"


def _status_label(descriptor: SecretManagerDescriptor) -> str:
    if descriptor.is_available is True:
        return "Available"
    if descriptor.is_available is False:
        return "Unavailable"
    return "Not checked"


def _manager_location(
    workspace: ProjectWorkspace,
    descriptor: SecretManagerDescriptor,
) -> str:
    if descriptor.kind == "embedded":
        return str(workspace.path)
    return getattr(descriptor.service, "target_path", "Service unavailable")


def _select_manager(
    workspace: ProjectWorkspace,
    descriptors: list[SecretManagerDescriptor],
    cache: dict[str, SecretManagerDescriptor],
) -> SecretManagerDescriptor:
    selected_id = st.selectbox(
        "Secret manager",
        options=[item.id for item in descriptors],
        index=next(
            (
                index
                for index, item in enumerate(descriptors)
                if item.is_active
            ),
            0,
        ),
        format_func=lambda item_id: _manager_label(
            next(item for item in descriptors if item.id == item_id)
        ),
        key="selected-secret-manager",
    )
    descriptor = next(item for item in descriptors if item.id == selected_id)

    status_col, refresh_col = st.columns((4, 1))
    probed = cache.get(descriptor.id)
    shown = probed or descriptor
    status_col.caption(
        f"{_status_label(shown)} · {_manager_location(workspace, descriptor)}"
    )
    if refresh_col.button(
        "Check",
        icon=":material/refresh:",
        width="stretch",
        key=f"check-secret-manager-{descriptor.id}",
    ):
        with st.spinner(f"Checking {descriptor.name}..."):
            cache[descriptor.id] = workspace.probe_secret_manager(descriptor.id)
        st.rerun()

    if descriptor.id not in cache:
        with st.spinner(f"Connecting to {descriptor.name}..."):
            cache[descriptor.id] = workspace.probe_secret_manager(descriptor.id)
    return cache[descriptor.id]


def _render_activation(
    workspace: ProjectWorkspace,
    descriptor: SecretManagerDescriptor,
    descriptors: list[SecretManagerDescriptor],
    cache: dict[str, SecretManagerDescriptor],
) -> None:
    if descriptor.is_active:
        st.success("Active project secret manager.", icon=":material/check_circle:")
        return

    active = next((item for item in descriptors if item.is_active), None)
    active_status = cache.get(active.id) if active else None
    active_unavailable = (
        active is not None
        and (
            active.is_available is False
            or (
                active_status is not None
                and active_status.is_available is False
            )
        )
    )
    migrate = True
    if active_unavailable:
        st.warning(
            "The active manager is unavailable, so its secrets cannot be copied."
        )
        migrate = not st.checkbox(
            "Switch without copying secrets",
            key=f"skip-secret-copy-{descriptor.id}",
        )

    if st.button(
        "Make active",
        type="primary",
        disabled=descriptor.is_available is not True,
        key=f"activate-secret-manager-{descriptor.id}",
    ):
        result = (
            workspace.use_embedded_secret_manager(migrate=migrate)
            if descriptor.kind == "embedded"
            else workspace.set_secret_manager(
                descriptor.service_uuid or "",
                migrate=migrate,
            )
        )
        if result.success:
            cache.clear()
            st.success(result.message)
            st.rerun()
        st.error(result.message)


def _render_keyfile(
    workspace: ProjectWorkspace,
    descriptor: SecretManagerDescriptor,
) -> None:
    manager = descriptor.manager
    service = descriptor.service
    if manager is None or not descriptor.supports_keyfile_export:
        st.caption("This manager does not support keyfile export.")
        return

    periodic = hasattr(service, "create_keyfile_secret_manager")
    password_key = f"keyfile-password-{descriptor.id}"
    if password_key not in st.session_state:
        st.session_state[password_key] = generate_pw(16)
    with st.form(f"keyfile-{descriptor.id}"):
        application = st.text_input("Application", value=descriptor.name)
        password = st.text_input(
            "Password",
            value=st.session_state[password_key],
        )
        period_label = (
            st.selectbox(
                "Renewal period",
                list(APPLICATION_PERIOD_OPTIONS),
                index=2,
            )
            if periodic
            else None
        )
        generate = st.form_submit_button(
            "Generate keyfile",
            type="primary",
        )

    if generate:
        try:
            keyfile_manager = manager
            if periodic:
                keyfile_manager = service.create_keyfile_secret_manager(
                    workspace.infrastructure,
                    period=APPLICATION_PERIOD_OPTIONS[period_label],
                    application_name=application,
                )
                workspace.commit()
            st.session_state[f"secret-keyfile-{descriptor.id}"] = (
                get_encrypted_access_keyfile(keyfile_manager, password)
            )
        except Exception as exc:
            st.error(f"Could not generate keyfile: {exc}")

    keyfile = st.session_state.get(f"secret-keyfile-{descriptor.id}")
    if keyfile:
        st.download_button(
            "Download keyfile",
            data=keyfile,
            file_name=f"{application.strip() or descriptor.name}.json",
            mime="application/json",
            icon=":material/download:",
            width="stretch",
        )


def _render_sync(workspace: ProjectWorkspace) -> None:
    st.caption("Store credentials from all running services in the active manager.")
    if not st.button(
        "Collect service secrets",
        icon=":material/sync:",
        width="stretch",
    ):
        return

    secret_count = 0
    service_count = 0
    name_uuid_map = {}
    with st.spinner("Collecting service secrets..."):
        for service in workspace.infrastructure.services():
            if service.state != "running":
                continue
            service_secrets = service.get_secrets()
            workspace.secrets.save_secret(service.uuid, service_secrets)
            name_uuid_map[service.name] = service.uuid
            secret_count += len(service_secrets)
            service_count += 1
        workspace.secrets.save_secret(
            "MLOX_SERVICE_NAME_UUID_MAP", name_uuid_map
        )
    st.success(
        f"Stored {secret_count} secrets from {service_count} running services."
    )


def _dedicated_settings(
    workspace: ProjectWorkspace,
    descriptor: SecretManagerDescriptor,
) -> tuple[Callable, object] | None:
    service = descriptor.service
    if service is None or service.state != "running":
        return None
    config = workspace.infrastructure.get_service_config(service)
    handler = (
        config.get_ui_handler("streamlit", "settings")
        if config is not None
        else None
    )
    if not handler or not getattr(handler, "is_secret_manager_settings", False):
        return None
    bundle = workspace.infrastructure.get_bundle_by_service(service)
    return (handler, bundle) if bundle is not None else None


def secrets() -> None:
    st.title("Secret Manager")
    st.caption("Choose the project secret store and manage its contents.")

    workspace = cast(ProjectWorkspace, st.session_state.mlox)
    descriptors = workspace.list_secret_managers()
    cache = _probe_cache(workspace)
    descriptor = _select_manager(workspace, descriptors, cache)

    _render_activation(workspace, descriptor, descriptors, cache)
    if descriptor.is_available is not True or descriptor.manager is None:
        st.error("This secret manager is unavailable.")
        return

    settings = _dedicated_settings(workspace, descriptor)
    tab_names = ["Secrets", "Actions"]
    if settings:
        tab_names.append("Settings")
    tabs = st.tabs(tab_names)
    secrets_tab, actions_tab = tabs[:2]

    with secrets_tab:
        render_secret_manager_settings(
            descriptor.manager,
            key_prefix=f"project-secret-manager-{descriptor.id}",
        )

    with actions_tab:
        if descriptor.is_active:
            st.markdown("#### Collect service secrets")
            _render_sync(workspace)
            st.divider()
        st.markdown("#### Application keyfile")
        _render_keyfile(workspace, descriptor)

    if settings:
        handler, bundle = settings
        with tabs[2]:
            handler(workspace.infrastructure, bundle, descriptor.service)


secrets()
