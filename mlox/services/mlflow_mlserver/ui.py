import logging
import pandas as pd
import streamlit as st

from typing import Dict, cast

from mlox.infra import Infrastructure, Bundle, ModelRegistry
from mlox.services.mlflow_mlserver.docker import MLFlowMLServerDockerService

logger = logging.getLogger(__name__)


def setup(infra: Infrastructure, bundle: Bundle) -> Dict | None:
    params: Dict = dict()

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

    svc = cast(ModelRegistry, svc)  # type: ignore
    models = svc.list_models()
    my_model = st.selectbox(
        "Select Model to Deploy",
        models,
        format_func=lambda x: f"{x['Model']}/{x['Version']}",
    )

    model_uri = f"{my_model['Model']}/{my_model['Version']}"
    st.write(model_uri)

    params["${MODEL_NAME}"] = model_uri
    params["${TRACKING_URI}"] = registry_secrets["service_url"]
    params["${TRACKING_USER}"] = registry_secrets["username"]
    params["${TRACKING_PW}"] = registry_secrets["password"]

    params["${MODEL_REGISTRY_UUID}"] = svc.uuid
    return params


def settings(
    infra: Infrastructure, bundle: Bundle, service: MLFlowMLServerDockerService
):
    st.header(f"Settings for service {service.name}")
    overview_tab, invoke_tab, versions_tab = st.tabs(
        ["Overview", "Invocation & Sample", "Model Versions"]
    )

    with overview_tab:
        info_col, cred_col = st.columns(2)
        with info_col:
            st.subheader("Service & Tracking")
            st.markdown(
                "\n".join(
                    [
                        f"- **Service URL:** `{service.service_url}`",
                        f"- **Tracking URI:** `{service.tracking_uri}`",
                        f"- **Model Identifier:** `{service.model}`",
                        f"- **Target Path:** `{service.target_path}`",
                    ]
                )
            )
        with cred_col:
            st.subheader("Credentials")
            st.code(
                "\n".join(
                    [
                        f"MLServer user: '{service.user}'",
                        f"MLServer password: '{service.pw}'",
                        f"Tracking user: '{service.tracking_user}'",
                        f"Tracking password: '{service.tracking_pw}'",
                    ]
                ),
                language="bash",
            )
            st.caption(
                f"Traefik basic auth hash: `{service.hashed_pw.replace('$', '\\$')}`",
            )

    with invoke_tab:
        st.subheader("Invoke via cURL")

        url = service.service_url
        if url.endswith("/"):
            url = url[:-1]
        example_curl = f"""
    curl -k -u '{service.user}:{service.pw}' \\
    {url}/invocations \\
    -H 'Content-Type: application/json' \\
    -d '{{"instances": [[0.0,1.0,2.0,3.0,4.0,5.0,6.0,7.0,8.0,9.1]]}}'
        """  # .replace("\\", "  \n").strip()
        st.write(
            f"Example cURL command to invoke the model:\n```bash\n{example_curl}\n```"
        )

    with versions_tab:
        st.subheader("Registered Versions")
        my_registry = service.get_registry()
        # st.write(service.registry_uuid)
        # st.write(my_registry)

        if not my_registry:
            st.warning("No model registry associated with this MLFlow MLServer.")
        else:
            names = my_registry.list_models(
                filter=f"name={service.model.split('/')[0]!r}"
            )

            # filter_string = f"name={service.model.split('/')[0]!r}"
            # for rm in client.search_model_versions(filter_string):
            #     # names.append([rm.name, rm.version, rm.current_stage, rm.source, rm.run_id])
            #     names.append(
            #         {
            #             # "name": rm.name,
            #             "alias": [str(a) for a in rm.aliases],
            #             "version": rm.version,
            #             "tags": [f"{k}:{v}" for k, v in rm.tags.items()],
            #             "current_stage": rm.current_stage,
            #             "creation_timestamp": rm.creation_timestamp,
            #             "run_id": rm.run_id,
            #             "status": rm.status,
            #             "last_updated_timestamp": rm.last_updated_timestamp,
            #             "description": rm.description,
            #             # "user_id": rm.user_id,
            #             "run_link": f"{service.service_url}#/experiments/{rm.run_id}/runs/{rm.run_id}",
            #         }
            #     )
            st.dataframe(
                pd.DataFrame(names),
                height=400,
                use_container_width=True,
                column_config={"Tags": st.column_config.ListColumn(width="small")},
            )
