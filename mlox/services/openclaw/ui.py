from typing import Dict

import streamlit as st

from mlox.infra import Bundle, Infrastructure
from mlox.services.openclaw.native import OpenClawNativeService


def setup(infra: Infrastructure, bundle: Bundle) -> Dict:  # noqa: ARG001
    params: Dict[str, str] = {}
    st.write("OpenClaw Native Configuration")

    channel = st.selectbox(
        "Install Channel",
        options=["latest", "beta", "dev"],
        index=0,
        help="Select the npm dist-tag to install for OpenClaw.",
    )
    params["${OPENCLAW_INSTALL_CHANNEL}"] = channel

    st.markdown(
        "After install, run `openclaw onboard --install-daemon` on the target server "
        "to complete the interactive setup."
    )
    return params


def settings(  # noqa: ARG001
    infra: Infrastructure, bundle: Bundle, service: OpenClawNativeService
):
    st.header(f"OpenClaw · {service.name}")

    st.metric("Status", service.state.title())
    st.text_input("Gateway URL", value=service.service_url, disabled=True)
    st.text_input(
        "Gateway Port",
        value=str(service.port),
        disabled=True,
    )

    st.subheader("Setup")
    st.markdown(
        "Run the onboarding wizard on the server to configure channels and credentials:"
    )
    st.code("openclaw onboard --install-daemon", language="bash")

    st.subheader("Docs")
    st.link_button("OpenClaw Docs", "https://docs.openclaw.ai")
    st.link_button("OpenClaw Repo", "https://github.com/openclaw/openclaw")
