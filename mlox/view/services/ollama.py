"""UI components for standalone Ollama service configuration."""

from typing import Dict

import streamlit as st

from mlox.infra import Bundle, Infrastructure
from mlox.services.ollama.docker import OllamaDockerService
from mlox.view.services.litellm import OLLAMA_MODELS


def setup(infra: Infrastructure, bundle: Bundle) -> Dict | None:  # noqa: ARG001
    params: Dict = {}

    st.write("Ollama Configuration")
    st.caption("Select models to pre-pull when the service starts.")

    selected_models: list[str] = []
    for category, models in OLLAMA_MODELS.items():
        with st.expander(category, expanded=category == "Small"):
            for model in models:
                if st.checkbox(model, key=f"ollama_standalone_{category}_{model}"):
                    selected_models.append(model)

    custom_models = st.text_input(
        "Additional models",
        value="",
        help="Comma-separated Ollama model names, for example llama3.2:1b,qwen2.5:0.5b.",
    )
    if custom_models.strip():
        selected_models.extend(
            model.strip() for model in custom_models.split(",") if model.strip()
        )

    params["${OLLAMA_MODELS}"] = list(dict.fromkeys(selected_models))
    return params


def settings(infra: Infrastructure, bundle: Bundle, service: OllamaDockerService):  # noqa: ARG001
    st.header(f"Ollama · {service.name}")

    overview_tab, invoke_tab = st.tabs(["Overview", "Invocation"])

    with overview_tab:
        info_col, cred_col = st.columns(2)
        with info_col:
            st.subheader("Service")
            st.markdown(
                "\n".join(
                    [
                        f"- **Service URL:** `{service.service_url}`",
                        f"- **Target Path:** `{service.target_path}`",
                        f"- **Keep Alive:** `{service.keep_alive}`",
                        f"- **Configured Models:** `{len(service.ollama_models)}`",
                    ]
                )
            )
            if service.ollama_models:
                st.markdown("- " + "\n- ".join(service.ollama_models))
        with cred_col:
            st.subheader("Credentials")
            st.code(
                "\n".join(
                    [
                        f"Ollama user: '{service.user}'",
                        f"Ollama password: '{service.pw}'",
                    ]
                ),
                language="bash",
            )

    with invoke_tab:
        url = service.service_url.rstrip("/")
        st.subheader("Native API")
        st.code(
            "\n".join(
                [
                    f"curl -k -u '{service.user}:{service.pw}' \\",
                    f"  {url}/api/tags",
                ]
            ),
            language="bash",
        )
        model = service.ollama_models[0] if service.ollama_models else "llama3.2:1b"
        st.code(
            "\n".join(
                [
                    f"curl -k -u '{service.user}:{service.pw}' \\",
                    f"  {url}/api/generate \\",
                    "  -H 'Content-Type: application/json' \\",
                    f"  -d '{{\"model\":\"{model}\",\"prompt\":\"Hello\",\"stream\":false}}'",
                ]
            ),
            language="bash",
        )
