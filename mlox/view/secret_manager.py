from typing import Any, cast

import pandas as pd
import streamlit as st

from mlox.infra import Infrastructure
from mlox.utils import generate_pw
from mlox.view.utils import st_hack_align
from mlox.secret_manager import get_encrypted_access_keyfile

APPLICATION_PERIOD_OPTIONS: dict[str, str] = {
    "1 hour": "1h",
    "8 hours": "8h",
    "24 hours": "24h",
    "7 days": "168h",
    "30 days": "720h",
    "90 days": "2160h",
}

# Lightweight CSS for badges, chips, and custom tables
st.markdown(
    """
    <style>
    .svc-badge {display:inline-block;padding:2px 8px;border-radius:999px;color:#fff;font-size:12px}
    .svc-chip {display:inline-block;padding:2px 8px;border-radius:999px;background:#111827;color:#e5e7eb;margin-right:6px;margin-bottom:4px;font-size:12px;border:1px solid #374151}
    .svc-table {width:100%;border-collapse:separate;border-spacing:0 6px}
    .svc-table th {text-align:left;padding:8px 10px;color:#94a3b8;font-size:13px}
    .svc-table td {background:#0b1220;padding:10px;border-top:1px solid #1f2937;border-bottom:1px solid #1f2937}
    .svc-pill {display:inline-block;padding:2px 6px;border:1px solid #334155;border-radius:6px;color:#cbd5e1;font-size:12px}
    .link-btn {display:inline-block;padding:6px 10px;background:#0ea5e9;color:#fff;border-radius:6px;text-decoration:none;margin-right:6px;margin-bottom:6px}
    .link-btn:hover {background:#0284c7}
    /* Style Streamlit metric blocks to match highlight color (#2E8B57) */
    div[data-testid="stMetric"] {
      background: rgba(56, 149, 97, 0.12); /* subtle SeaGreen tint */
      border: 1px solid rgba(46, 139, 87, 0.6);
      border-radius: 16px;
      padding: 10px;
    }
    div[data-testid="stMetric"] label {color:#cbd5e1}
    div[data-testid="stMetricValue"] {color:#2E8B57}
    div[data-testid="stMetricValue"] * {color:#2E8B57 !important}
    </style>
    """,
    unsafe_allow_html=True,
)


def save_infra() -> None:
    with st.spinner("Saving infrastructure..."):
        st.session_state.mlox.save_infrastructure()


def _collect_secret_manager_rows(infra: Infrastructure) -> list[dict[str, Any]]:
    secret_manager_rows: list[dict[str, Any]] = []
    for service in infra.filter_by_group("secret-manager"):
        bundle = infra.get_bundle_by_service(service)
        if not bundle:
            continue
        secret_manager_rows.append(
            {
                "ip": bundle.server.ip,
                "server": bundle.name,
                "name": service.name,
                "path": service.target_path,
                "service": service,
                "bundle": bundle,
            }
        )
    return secret_manager_rows


def _render_overview(secret_manager_rows: list[dict[str, Any]]) -> None:
    total_servers = {row["server"] for row in secret_manager_rows}
    with st.container():
        col_left, col_right = st.columns(2)
        col_left.metric("Secret Manager Services", len(secret_manager_rows))
        col_right.metric("Servers", len(total_servers) if secret_manager_rows else 0)
        st.caption(
            "Select a secret manager below to sync secrets or adjust its settings."
        )


def secrets() -> None:
    st.title("Secret Manager")
    st.caption("Manage secret stores across your infrastructure bundles.")
    st.divider()

    try:
        infra = cast(Infrastructure, st.session_state.mlox.infra)
    except Exception:  # pragma: no cover - defensive path for UI runtime
        st.error("Could not load infrastructure configuration.")
        st.stop()

    secret_manager_rows = _collect_secret_manager_rows(infra)
    if not secret_manager_rows:
        st.info(
            "No secret manager services found. Deploy one to manage secrets centrally."
        )
        return

    _render_overview(secret_manager_rows)
    st.subheader("Available Secret Managers")

    table = pd.DataFrame(
        secret_manager_rows,
        columns=["ip", "server", "name", "path", "service", "bundle"],
    )
    selection = st.dataframe(
        table[["server", "name", "path"]],
        hide_index=True,
        selection_mode="single-row",
        width="stretch",
        on_select="rerun",
    )

    selected_rows = selection.get("selection", {}).get("rows", [])
    if not selected_rows:
        st.info("Select a secret manager from the table to see details.")
        return

    selected_idx = selected_rows[0]
    selected = secret_manager_rows[selected_idx]
    bundle = selected["bundle"]
    secret_manager_service = selected["service"]
    secret_manager = secret_manager_service.get_secret_manager(infra)

    st.divider()
    st.subheader("Selected Secret Manager")
    col_details, col_path = st.columns((2, 1))
    with col_details:
        st.markdown(f"**Server**: {selected['server']}")
        st.markdown(f"**Service**: {secret_manager_service.name}")
        st.markdown(f"**Status**: {secret_manager_service.state.title()}")
    with col_path:
        st.markdown("**Path**")
        st.code(selected["path"], language="bash")

    supports_periodic_credentials = hasattr(
        secret_manager_service, "create_keyfile_secret_manager"
    )
    if st.toggle(
        "Download Application Keyfile"
        if supports_periodic_credentials
        else "Download Keyfile",
        value=False,
        key=f"toggle_download_access_keyfile_{secret_manager_service.name}",
        help=(
            "Create a periodic scoped application credential and download its "
            "encrypted access keyfile."
            if supports_periodic_credentials
            else "Download the encrypted access keyfile for this secret manager."
        ),
    ):
        with st.container(horizontal_alignment="distribute", border=True):
            st.markdown(
                "#### Download Application Keyfile"
                if supports_periodic_credentials
                else "#### Download Access Keyfile"
            )
            if supports_periodic_credentials:
                st.info(
                    "OpenBao creates a periodic, renewable token for this application. "
                    "The application must renew it before the selected period expires. "
                    "Generating the same application again rotates its previous token."
                )
            else:
                st.caption(
                    "Download the access information required to connect to this secret manager."
                )
            c1, c2, c3 = st.columns(3)
            application_name = c1.text_input(
                "Application",
                value=secret_manager_service.name,
                key=f"keyfile_application_{secret_manager_service.name}",
            )
            keyfile_name = f"{application_name.strip() or secret_manager_service.name}.json"
            keyfile_pw = c2.text_input(
                "Password",
                value=generate_pw(16),
                key=f"keyfile_pw_{secret_manager_service.name}",
            )
            period_label = "24 hours"
            if supports_periodic_credentials:
                period_label = c3.selectbox(
                    "Renewal period",
                    options=list(APPLICATION_PERIOD_OPTIONS.keys()),
                    index=2,
                    key=f"keyfile_period_{secret_manager_service.name}",
                )

            generated_key = f"generated_access_keyfile_{secret_manager_service.uuid}"
            signature_key = f"{generated_key}_signature"
            keyfile_signature = (
                application_name,
                keyfile_pw,
                APPLICATION_PERIOD_OPTIONS.get(period_label)
                if supports_periodic_credentials
                else None,
            )
            if supports_periodic_credentials:
                period = APPLICATION_PERIOD_OPTIONS[period_label]
                if st.session_state.get(signature_key) != keyfile_signature:
                    keyfile_secret_manager = (
                        secret_manager_service.create_keyfile_secret_manager(
                            infra,
                            period=period,
                            application_name=application_name,
                        )
                    )
                    st.session_state[generated_key] = get_encrypted_access_keyfile(
                        keyfile_secret_manager, keyfile_pw
                    )
                    st.session_state[signature_key] = keyfile_signature
                    try:
                        st.session_state.mlox.save_infrastructure()
                    except Exception:
                        pass
                encrypted_keyfile = st.session_state[generated_key]
                st.caption(f"Renewal period: `{period}`")
            else:
                encrypted_keyfile = get_encrypted_access_keyfile(
                    secret_manager, keyfile_pw
                )

            st_hack_align(c3)
            c3.download_button(
                "Download Application Keyfile"
                if supports_periodic_credentials
                else "Download Keyfile",
                data=encrypted_keyfile,
                file_name=keyfile_name,
                mime="application/json",
                icon=":material/download:",
                type="primary",
                key=f"download_access_keyfile_{secret_manager_service.name}",
                width="stretch",
            )

    with st.container():
        st.markdown("#### Sync Secrets from Active Services")
        st.caption(
            "Collect secrets from all running services and store them in this secret manager."
        )
        if st.button(
            "Collect service secrets",
            type="primary",
            width="stretch",
            key=f"collect-secrets-{secret_manager_service.uuid}",
        ):
            secrets_cnt = 0
            service_cnt = 0
            name_uuid_map = {}
            with st.spinner("Collecting secrets from running services..."):
                for service in infra.services():
                    if service.state != "running":
                        continue
                    name_uuid_map[service.name] = service.uuid
                    service_cnt += 1
                    service_secrets = service.get_secrets()
                    secret_manager.save_secret(service.uuid, service_secrets)
                    secrets_cnt += len(service_secrets.keys())
            secret_manager.save_secret("MLOX_SERVICE_NAME_UUID_MAP", name_uuid_map)
            st.success(
                f"Collected {secrets_cnt} secrets from {service_cnt} active services."
            )

    config = infra.get_service_config(secret_manager_service)
    callable_settings_func = config.get_ui_handler("streamlit", "settings")
    if callable_settings_func and secret_manager_service.state == "running":
        st.divider()
        st.subheader("Service Settings")
        callable_settings_func(infra, bundle, secret_manager_service)


secrets()
