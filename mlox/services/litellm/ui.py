"""UI components for LiteLLM + Ollama service configuration."""

from typing import Dict

import streamlit as st

from mlox.infra import Bundle, Infrastructure
from mlox.services.litellm.docker import LiteLLMDockerService

# Curated list of popular Ollama models organized by size
OLLAMA_MODELS = {
    "Tiny (< 2GB)": [
        "tinyllama",
        "qwen2.5:0.5b",
        "deepseek-r1:1.5b",
        "llama3.2:1b",
        "phi3.5:3.8b",
    ],
    "Small (2-5GB)": [
        "llama3.2:3b",
        "qwen2.5:3b",
        "phi3:3.8b",
        "gemma2:2b",
        "mistral:7b",
    ],
    "Medium (5-10GB)": [
        "qwen2.5:7b",
        "llama3.1:8b",
        "mistral-nemo:12b",
        "gemma2:9b",
        "phi3:14b",
    ],
    "Large (> 10GB)": [
        "qwen2.5:14b",
        "llama3.1:70b",
        "deepseek-r1:70b",
        "qwen2.5:32b",
        "mixtral:8x7b",
    ],
}


def setup(infra: Infrastructure, bundle: Bundle) -> Dict:  # noqa: ARG001
    """Configure LiteLLM + Ollama service during setup.

    Args:
        infra: Infrastructure instance (unused but required by interface)
        bundle: Bundle instance (unused but required by interface)

    Returns:
        Dictionary of configuration parameters for the service
    """
    params: Dict = {}
    st.write("LiteLLM + Ollama Configuration")

    # OpenAI key input
    c1, _c2 = st.columns(2)
    openai_key = c1.text_input("OpenAI Key (optional)", key="openai_key")
    params["${OPENAI_KEY}"] = openai_key

    # Ollama model selection
    st.markdown("### Ollama Model Selection")
    st.markdown(
        "Select which Ollama models to pre-install. "
        "Models will be downloaded when the service starts. "
        "You can always add more models later via the Ollama CLI."
    )

    # Flatten model list for multiselect
    all_models = []
    for category, models in OLLAMA_MODELS.items():
        all_models.extend(models)

    # Create expandable sections for each category
    with st.expander("📦 Browse models by size", expanded=True):
        for category, models in OLLAMA_MODELS.items():
            st.markdown(f"**{category}**")
            st.markdown("- " + "\n- ".join(models))

    # Default selection (tiny models)
    default_models = ["tinyllama", "llama3.2:1b", "deepseek-r1:1.5b"]

    selected_models = st.multiselect(
        "Select models to pre-install",
        options=all_models,
        default=default_models,
        help="Choose one or more models. We recommend starting with smaller models for faster setup.",
    )

    # Warning if no models selected
    if not selected_models:
        st.warning("⚠️ No models selected. Ollama will start without any pre-installed models.")

    # Show estimated disk usage
    if selected_models:
        st.info(f"✅ {len(selected_models)} model(s) selected")

    # Store selected models in params for the service
    params["${OLLAMA_MODELS}"] = ",".join(selected_models) if selected_models else ""

    return params


def settings(infra: Infrastructure, bundle: Bundle, service: LiteLLMDockerService):  # noqa: ARG001
    """Display settings for an installed LiteLLM + Ollama service.

    Args:
        infra: Infrastructure instance (unused but required by interface)
        bundle: Bundle instance containing server information
        service: The LiteLLM service instance
    """
    st.header(f"Settings for service {service.name}")
    st.write(f"IP: {bundle.server.ip}")

    st.write(f'User and Password: "{service.ui_user}:{service.ui_pw}"')
