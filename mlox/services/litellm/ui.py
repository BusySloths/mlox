import json  # For parsing JSON
import pandas as pd  # Optional: for displaying as a table
import streamlit as st

from typing import List, Dict


from mlox.services.litellm.docker import LiteLLMDockerService
from mlox.infra import Infrastructure, Bundle


def setup(infra: Infrastructure, bundle: Bundle) -> Dict:
    params: Dict = dict()
    st.write("LiteLLM")

    c1, c2 = st.columns(2)
    openai_key = c1.text_input("OpenAI Key", key="openai_key")
    params["${OPENAI_KEY}"] = openai_key

    return params


def settings(infra: Infrastructure, bundle: Bundle, service: LiteLLMDockerService):
    st.header(f"Settings for service {service.name}")
    st.write(f"IP: {bundle.server.ip}")

    st.write(f'User and Password: "{service.ui_user}:{service.ui_pw}"')
