import json
import logging

import pandas as pd
import requests
import streamlit as st

from typing import Dict, cast

from mlox.infra import Bundle, Infrastructure, ModelRegistry
from mlox.services.mlflow_gateway.docker import MLFlowGatewayDockerService

logger = logging.getLogger(__name__)


def setup(infra: Infrastructure, bundle: Bundle) -> Dict | None:
    params: Dict = {}

    registries = infra.filter_by_group(group="model-registry")
    if len(registries) == 0:
        st.warning("No model registries found. Please add one first.")
        return None

    svc = st.selectbox(
        "Select Model Registry",
        registries,
        format_func=lambda x: f"{x.name} @ {x.service_url}",
    )
    registry_secrets = svc.get_secrets()
    if not registry_secrets:
        st.warning(
            f"No credentials found for model registry {svc.name}. Please add them first."
        )
        return None

    requirements_txt = st.text_area(
        "Additional gateway requirements.txt",
        value="",
        height=180,
        help=(
            "Optional packages installed into the gateway image at startup. "
            "Use this for shared lightweight dependencies needed by multiple models."
        ),
    )
    cache_max_models = st.number_input(
        "Max cached models",
        min_value=1,
        max_value=100,
        value=10,
        step=1,
        help="LRU limit for loaded model objects kept in the gateway process.",
    )
    cache_ttl_days = st.number_input(
        "Cache TTL days",
        min_value=0.0,
        max_value=365.0,
        value=10.0,
        step=1.0,
        help="Models not used for this many days are retired from the cache. Use 0 to disable TTL eviction.",
    )

    params["${TRACKING_URI}"] = registry_secrets["service_url"]
    params["${TRACKING_USER}"] = registry_secrets["username"]
    params["${TRACKING_PW}"] = registry_secrets["password"]
    params["${GATEWAY_REQUIREMENTS_TXT}"] = requirements_txt
    params["${GATEWAY_CACHE_MAX_MODELS}"] = str(int(cache_max_models))
    params["${GATEWAY_CACHE_TTL_DAYS}"] = str(cache_ttl_days)
    params["${MODEL_REGISTRY_UUID}"] = svc.uuid
    return params


def settings(
    infra: Infrastructure, bundle: Bundle, service: MLFlowGatewayDockerService
):
    st.header(f"Settings for service {service.name}")
    overview_tab, invoke_tab, cache_tab, versions_tab = st.tabs(
        ["Overview", "Invocation", "Cache", "Registry Models"]
    )

    with overview_tab:
        c1, c2 = st.columns(2)
        with c1:
            st.subheader("Service & Tracking")
            st.markdown(
                "\n".join(
                    [
                        f"- **Service URL:** `{service.service_url}`",
                        f"- **Tracking URI:** `{service.tracking_uri}`",
                        f"- **Target Path:** `{service.target_path}`",
                        f"- **Max Cached Models:** `{service.cache_max_models}`",
                        f"- **Cache TTL Days:** `{service.cache_ttl_days}`",
                    ]
                )
            )
        with c2:
            st.subheader("Credentials")
            st.code(
                "\n".join(
                    [
                        f"Gateway user: '{service.user}'",
                        f"Gateway password: '{service.pw}'",
                        f"Tracking user: '{service.tracking_user}'",
                        f"Tracking password: '{service.tracking_pw}'",
                    ]
                ),
                language="bash",
            )
        if service.requirements_txt.strip():
            st.subheader("Additional Requirements")
            st.code(service.requirements_txt, language="text")

    with invoke_tab:
        my_registry = service.get_registry()
        model_name = "ModelName"
        model_version = "1"
        if my_registry:
            models = my_registry.list_models()
            selected = st.selectbox(
                "Select Example Model",
                models,
                format_func=lambda x: f"{x['Model']}/{x['Version']}",
            )
            if selected:
                model_name = selected["Model"]
                model_version = selected["Version"]

        payload = {
            "input_data": [[0.0, 1.0, 2.0]],
            "params": {},
            "registry_model_name": model_name,
            "registry_model_version": model_version,
        }
        alias_payload = {
            "input_data": [[0.0, 1.0, 2.0]],
            "params": {},
            "registry_model_name": model_name,
            "registry_model_alias": "champion",
        }
        st.caption("Version-based request")
        st.code(
            "\n".join(
                [
                    f"curl -k -u '{service.user}:{service.pw}' \\",
                    f"  {service.service_url.rstrip('/')}/prod/predict \\",
                    "  -H 'Content-Type: application/json' \\",
                    f"  -d '{json.dumps(payload)}'",
                ]
            ),
            language="bash",
        )
        st.caption("Alias-based request")
        st.code(
            "\n".join(
                [
                    f"curl -k -u '{service.user}:{service.pw}' \\",
                    f"  {service.service_url.rstrip('/')}/prod/predict \\",
                    "  -H 'Content-Type: application/json' \\",
                    f"  -d '{json.dumps(alias_payload)}'",
                ]
            ),
            language="bash",
        )

    with cache_tab:
        st.subheader("Gateway Cache")
        if st.button("Refresh Cache"):
            st.rerun()
        try:
            response = requests.get(
                f"{service.service_url.rstrip('/')}/cache",
                auth=(service.user, service.pw),
                verify=False,
                timeout=10,
            )
            if response.ok:
                cache_cfg = response.json().get("cache", {})
                if cache_cfg:
                    st.caption(
                        f"max_models={cache_cfg.get('max_models')} | "
                        f"ttl_days={cache_cfg.get('ttl_days')}"
                    )
                cached = response.json().get("cached_models", [])
                if cached:
                    st.dataframe(pd.DataFrame(cached), hide_index=True, width="stretch")
                else:
                    st.info("No models cached yet.")
            else:
                st.warning(f"Gateway returned HTTP {response.status_code}.")
        except Exception as exc:
            logger.info("Could not load gateway cache state: %s", exc)
            st.info("Cache state is available after the service is running.")

    with versions_tab:
        my_registry = cast(ModelRegistry | None, service.get_registry())
        if not my_registry:
            st.warning("No model registry associated with this MLflow Gateway.")
        else:
            models = my_registry.list_models()
            if not models:
                st.info("No registered models found.")
            else:
                st.dataframe(
                    pd.DataFrame(models),
                    hide_index=True,
                    width="stretch",
                    column_config={"Tags": st.column_config.ListColumn(width="small")},
                )
