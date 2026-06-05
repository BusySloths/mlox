"""Streamlit UI helpers for the OpenBao service."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd
import streamlit as st

from mlox.infra import Infrastructure, Bundle
from mlox.secret_manager import get_encrypted_access_keyfile
from mlox.utils import generate_pw
from mlox.view.services.common import save_to_secret_store

from mlox.services.openbao import OpenBaoDockerService


APPLICATION_PERIOD_OPTIONS: dict[str, str] = {
    "1 hour": "1h",
    "8 hours": "8h",
    "24 hours": "24h",
    "7 days": "168h",
    "30 days": "720h",
    "90 days": "2160h",
}


def _format_secret_value(value: Any) -> str:
    if isinstance(value, dict):
        return json.dumps(value, indent=2)
    if isinstance(value, str):
        return value
    return json.dumps(value, indent=2, default=str)


def setup(infra: Infrastructure, bundle: Bundle):
    """OpenBao production mode bootstraps itself after the first start."""
    return {}


def _mask_secret(value: str) -> str:
    if not value:
        return ""
    if len(value) <= 8:
        return "****"
    return f"{value[:4]}...{value[-4:]}"


def _save_infra() -> None:
    try:
        st.session_state.mlox.save_infrastructure()
    except Exception:
        pass


def _format_ttl(seconds: int | str | None) -> str:
    try:
        value = int(seconds or 0)
    except (TypeError, ValueError):
        return "-"
    if value <= 0:
        return "expired"
    if value >= 86400:
        return f"{value // 86400}d"
    if value >= 3600:
        return f"{value // 3600}h"
    if value >= 60:
        return f"{value // 60}m"
    return f"{value}s"


def _credential_rows(service: OpenBaoDockerService) -> pd.DataFrame:
    rows = []
    for name, credential in sorted(service.application_credentials.items()):
        accessor = str(credential.get("accessor", ""))
        rows.append(
            {
                "Application": name,
                "Status": credential.get("status", "active"),
                "TTL": _format_ttl(credential.get("lease_duration")),
                "Renewable": bool(credential.get("renewable", True)),
                "Period": credential.get("period") or "-",
                "Accessor": f"{accessor[:12]}..." if accessor else "-",
            }
        )
    return pd.DataFrame(rows)


def _usage_markdown() -> str:
    usage_path = Path(__file__).resolve().parents[2] / "services/openbao/USAGE.md"
    try:
        return usage_path.read_text(encoding="utf-8")
    except OSError:
        return ""


def settings(infra: Infrastructure, bundle: Bundle, service: OpenBaoDockerService):
    key = f"openbao_secret_manager_{service.uuid}"
    if key not in st.session_state:
        st.session_state[key] = service.get_secret_manager(infra)
    manager = st.session_state[key]

    service_token_error: Exception | None = None
    try:
        status = manager.seal_status()
    except Exception as exc:
        service_token_error = exc
        try:
            status = service.get_root_secret_manager(infra).seal_status()
        except Exception:
            status = {}

    initialized = bool(status.get("initialized", bool(service.root_token)))
    sealed = bool(status.get("sealed", False)) if status else False
    service_token_expired = (
        bool(service_token_error)
        or bool(service.client_token and service.client_token_lease_duration <= 0)
    )
    status_cols = st.columns(4)
    status_cols[0].metric("Initialized", "Yes" if initialized else "No")
    status_cols[1].metric("Seal", "Sealed" if sealed else "Open")
    status_cols[2].metric("Client TTL", _format_ttl(service.client_token_lease_duration))
    status_cols[3].metric("Applications", len(service.application_credentials))

    usage_markdown = _usage_markdown()
    if usage_markdown:
        with st.expander("How to use this secret manager", expanded=False):
            st.markdown(usage_markdown)

    access_tab, apps_tab, secrets_tab, recovery_tab = st.tabs(
        ["Access", "Applications", "Secrets", "Recovery"]
    )

    with access_tab:
        st.markdown("#### Browser Login")
        st.caption("Use userpass for the OpenBao UI. Root credentials stay in recovery.")
        login_cols = st.columns(3)
        login_cols[0].text_input(
            "Method",
            value=service.userpass_path,
            disabled=True,
            key=f"openbao_userpass_path_{service.uuid}",
        )
        login_cols[1].text_input(
            "Username",
            value=service.admin_username,
            disabled=True,
            key=f"openbao_admin_username_{service.uuid}",
        )
        if service.admin_password and login_cols[2].toggle(
            "Show password",
            value=False,
            key=f"openbao_show_admin_password_{service.uuid}",
        ):
            st.text_input(
                "Password",
                value=service.admin_password,
                disabled=True,
                type="default",
                key=f"openbao_admin_password_{service.uuid}",
            )

        st.markdown("#### mlox Service Token")
        if service_token_expired:
            st.warning(
                "The mlox service token may be expired or invalid. Secret browsing "
                "can fail until it is replaced. Use `Rotate client token` to create "
                "a fresh scoped token; mlox will save the updated token automatically."
            )
        else:
            st.info(
                "The mlox service token is the scoped credential used for normal "
                "mlox secret operations. Root remains reserved for recovery and "
                "credential administration."
            )
        token_cols = st.columns(4)
        token_cols[0].text_input(
            "Token",
            value=_mask_secret(service.client_token),
            disabled=True,
            key=f"openbao_client_token_masked_{service.uuid}",
        )
        token_cols[1].text_input(
            "Accessor",
            value=service.client_token_accessor or "-",
            disabled=True,
            key=f"openbao_client_accessor_{service.uuid}",
        )
        token_cols[2].text_input(
            "Renewable",
            value=str(service.client_token_renewable),
            disabled=True,
            key=f"openbao_client_renewable_{service.uuid}",
        )
        token_cols[3].text_input(
            "Lease",
            value=_format_ttl(service.client_token_lease_duration),
            disabled=True,
            key=f"openbao_client_lease_{service.uuid}",
        )
        action_cols = st.columns(2)
        if action_cols[0].button(
            "Renew client token",
            type="primary",
            key=f"openbao_renew_client_token_{service.uuid}",
            width="stretch",
        ):
            try:
                service.renew_client_token(infra)
                st.session_state.pop(key, None)
                _save_infra()
                st.success("OpenBao client token renewed.")
                st.rerun()
            except Exception as exc:
                st.error(
                    "Could not renew the mlox service token. If it already expired, "
                    "use `Rotate client token` to create and save a replacement."
                )
        if action_cols[1].button(
            "Rotate client token",
            key=f"openbao_rotate_client_token_{service.uuid}",
            width="stretch",
        ):
            try:
                old_token = service.client_token
                service.rotate_client_token(infra)
                st.session_state.pop(key, None)
                if service.client_token != old_token:
                    _save_infra()
                st.success("OpenBao client token rotated.")
                st.rerun()
            except Exception as exc:
                st.error(f"Could not rotate OpenBao client token: {exc}")

    with apps_tab:
        st.markdown("#### Application Credentials")
        st.caption(
            "Each application has a renewable scoped token. mlox stores only the accessor."
        )
        with st.form(f"openbao_add_application_credential_{service.uuid}"):
            add_cols = st.columns(3)
            new_application = add_cols[0].text_input(
                "Application",
                placeholder="my-app",
                key=f"openbao_new_application_{service.uuid}",
            )
            new_period_label = add_cols[1].selectbox(
                "Renewal period",
                options=list(APPLICATION_PERIOD_OPTIONS.keys()),
                index=2,
                key=f"openbao_new_application_ttl_{service.uuid}",
            )
            with add_cols[2]:
                st.markdown("&nbsp;", unsafe_allow_html=True)
                submitted = st.form_submit_button(
                    "Add credential",
                    type="primary",
                    width="stretch",
                )
            if submitted:
                try:
                    period = APPLICATION_PERIOD_OPTIONS[new_period_label]
                    service.create_application_credential(
                        new_application,
                        infra,
                        period=period,
                    )
                    _save_infra()
                    st.success(f"Added credential for {new_application}.")
                    st.rerun()
                except Exception as exc:
                    st.error(f"Could not add application credential: {exc}")

        if st.button(
            "Refresh credential status",
            key=f"openbao_refresh_application_credentials_{service.uuid}",
        ):
            try:
                service.refresh_application_credentials(infra)
                _save_infra()
                st.rerun()
            except Exception as exc:
                st.error(f"Could not refresh application credentials: {exc}")

        credentials_df = _credential_rows(service)
        if credentials_df.empty:
            st.info("No application credentials have been generated yet.")
        else:
            selection = st.dataframe(
                credentials_df,
                hide_index=True,
                selection_mode="single-row",
                width="stretch",
                on_select="rerun",
                key=f"openbao_application_credentials_table_{service.uuid}",
            )
            selected_rows = selection.get("selection", {}).get("rows", [])
            if selected_rows:
                selected_application = credentials_df.iloc[selected_rows[0]][
                    "Application"
                ]
                st.markdown(f"#### `{selected_application}`")
                selected = service.application_credentials.get(
                    str(selected_application), {}
                )
                detail_cols = st.columns(4)
                detail_cols[0].metric("Status", str(selected.get("status", "active")))
                detail_cols[1].metric(
                    "TTL", _format_ttl(selected.get("lease_duration"))
                )
                detail_cols[2].metric(
                    "Renewable", "Yes" if selected.get("renewable", True) else "No"
                )
                detail_cols[3].metric("Period", selected.get("period") or "-")

                app_action_cols = st.columns(5)
                keyfile_pw = app_action_cols[0].text_input(
                    "Keyfile password",
                    value=generate_pw(16),
                    key=f"openbao_selected_keyfile_pw_{service.uuid}_{selected_application}",
                )
                period_label = app_action_cols[1].selectbox(
                    "Rotation period",
                    options=list(APPLICATION_PERIOD_OPTIONS.keys()),
                    index=2,
                    key=f"openbao_selected_keyfile_ttl_{service.uuid}_{selected_application}",
                )
                if app_action_cols[2].button(
                    "Renew",
                    type="primary",
                    key=f"openbao_renew_application_{service.uuid}_{selected_application}",
                    width="stretch",
                ):
                    try:
                        service.renew_application_credential(
                            str(selected_application), infra
                        )
                        _save_infra()
                        st.success(f"Renewed {selected_application}.")
                        st.rerun()
                    except Exception as exc:
                        st.error(f"Could not renew {selected_application}: {exc}")
                if app_action_cols[3].button(
                    "Revoke",
                    key=f"openbao_revoke_application_{service.uuid}_{selected_application}",
                    width="stretch",
                ):
                    try:
                        service.revoke_application_credential(
                            str(selected_application), infra
                        )
                        _save_infra()
                        st.success(f"Revoked {selected_application}.")
                        st.rerun()
                    except Exception as exc:
                        st.error(f"Could not revoke {selected_application}: {exc}")

                period = APPLICATION_PERIOD_OPTIONS[period_label]
                download_state_key = (
                    f"openbao_selected_keyfile_{service.uuid}_{selected_application}"
                )
                signature_key = f"{download_state_key}_signature"
                signature = (selected_application, keyfile_pw, period_label)
                if app_action_cols[4].button(
                    "Rotate keyfile",
                    key=f"openbao_rotate_application_{service.uuid}_{selected_application}",
                    width="stretch",
                ):
                    try:
                        keyfile_manager = service.create_keyfile_secret_manager(
                            infra,
                            period=period,
                            application_name=str(selected_application),
                        )
                        st.session_state[download_state_key] = (
                            get_encrypted_access_keyfile(keyfile_manager, keyfile_pw)
                        )
                        st.session_state[signature_key] = signature
                        _save_infra()
                    except Exception as exc:
                        st.error(f"Could not rotate {selected_application}: {exc}")
                if (
                    download_state_key in st.session_state
                    and st.session_state.get(signature_key) == signature
                ):
                    st.download_button(
                        "Download rotated keyfile",
                        data=st.session_state[download_state_key],
                        file_name=f"{selected_application}.json",
                        mime="application/json",
                        icon=":material/download:",
                        type="primary",
                        key=f"openbao_download_selected_keyfile_{service.uuid}_{selected_application}",
                    )

    with secrets_tab:
        if sealed:
            st.warning("OpenBao is sealed. Unseal it in the Recovery tab first.")
        elif service_token_expired:
            st.warning(
                "Secret browsing is disabled because the mlox service token may be "
                "expired or invalid. Rotate the client token in the Access tab, then "
                "return here."
            )
        else:
            try:
                secrets = manager.list_secrets(keys_only=True)
            except Exception as exc:
                st.warning(f"Could not list OpenBao secrets: {exc}")
                secrets = {}

            df = pd.DataFrame(
                [[name, "****"] for name in secrets.keys()], columns=["Key", "Value"]
            )
            selection = st.dataframe(
                df,
                hide_index=True,
                selection_mode="single-row",
                width="stretch",
                on_select="rerun",
                key=f"openbao_secrets_table_{service.uuid}",
            )

            if len(selection["selection"]["rows"]) > 0:
                idx = selection["selection"]["rows"][0]
                secret_key = df.iloc[idx]["Key"]
                secret_value = manager.load_secret(secret_key)
                if secret_value is None:
                    st.info("Could not load secret from OpenBao.")
                else:
                    save_to_secret_store(infra, secret_key, secret_value)
                    st.markdown(f"#### `{secret_key}`")
                    formatted = _format_secret_value(secret_value)
                    if isinstance(secret_value, dict) and st.toggle(
                        "Tree View",
                        value=False,
                        key=f"openbao_tree_{secret_key}",
                    ):
                        st.write(secret_value)
                    else:
                        st.text_area(
                            "Value",
                            value=formatted,
                            height=240,
                            disabled=True,
                            key=f"openbao_value_{secret_key}",
                        )
                    st.download_button(
                        "Download secret",
                        data=formatted,
                        file_name=f"{secret_key.lower()}.json",
                        mime="application/json",
                        icon=":material/download:",
                        key=f"openbao_download_{secret_key}",
                    )
            else:
                with st.form("openbao_add_secret"):
                    name = st.text_input("Key")
                    value = st.text_area("Value", placeholder="JSON or text")
                    if st.form_submit_button("Add Secret"):
                        manager.save_secret(name, value)
                        st.rerun()

    with recovery_tab:
        st.markdown("#### Seal Recovery")
        if sealed:
            if not service.unseal_keys:
                st.warning("OpenBao is sealed and no unseal key is stored in mlox state.")
            elif st.button(
                "Unseal",
                type="primary",
                icon=":material/lock_open:",
                key=f"openbao_unseal_{service.uuid}",
            ):
                for unseal_key in service.unseal_keys:
                    status = manager.unseal(unseal_key)
                    if not bool(status.get("sealed", True)):
                        break
                if bool(status.get("sealed", True)):
                    st.error("OpenBao remained sealed after submitting stored unseal keys.")
                else:
                    st.success("OpenBao unsealed.")
                    st.rerun()
        else:
            st.info("OpenBao is unsealed.")

        st.markdown("#### Emergency Material")
        st.warning("Use root and unseal material only for recovery or bootstrap tasks.")
        st.write(f"Root Token: `{_mask_secret(service.root_token)}`")
        if service.root_token and st.toggle(
            "Show full root token",
            value=False,
            key=f"openbao_show_root_token_{service.uuid}",
        ):
            st.text_input(
                "Root Token",
                value=service.root_token,
                disabled=True,
                type="default",
                key=f"openbao_root_token_{service.uuid}",
            )
        st.write(f"Unseal Keys: `{len(service.unseal_keys)}`")
        if service.unseal_keys and st.toggle(
            "Show unseal keys",
            value=False,
            key=f"openbao_show_unseal_keys_{service.uuid}",
        ):
            for idx, unseal_key in enumerate(service.unseal_keys, start=1):
                st.text_input(
                    f"Unseal Key {idx}",
                    value=unseal_key,
                    disabled=True,
                    type="default",
                    key=f"openbao_unseal_key_{service.uuid}_{idx}",
                )
