"""Streamlit setup for the DuckLake connector."""
import streamlit as st

from mlox.service import ServiceCapability


def setup(infra, bundle):
    postgres = [s for s in infra.services() if str(getattr(s, "service_config_id", "")).startswith("postgres-")]
    storage = [s for s in infra.services() if ServiceCapability.S3_OBJECT_STORAGE in getattr(s, "capabilities", set())]
    managers = list(infra.filter_by_group("secret-manager"))
    if not postgres or not storage or not managers:
        st.error("DuckLake requires PostgreSQL, object storage, and a secret manager.")
        return None
    pg = st.selectbox("PostgreSQL service", postgres, format_func=lambda service: service.name)
    s3 = st.selectbox("Object storage service", storage, format_func=lambda service: service.name)
    manager = st.selectbox("Secret manager", managers, format_func=lambda service: service.name)
    return {
        "${POSTGRES_SERVICE_UUID}": pg.uuid,
        "${STORAGE_SERVICE_UUID}": s3.uuid,
        "${SECRET_MANAGER_UUID}": manager.uuid,
        "${POSTGRES_SECRET_NAME}": st.text_input("PostgreSQL connection secret"),
        "${S3_SECRET_NAME}": st.text_input("S3 connection secret"),
        "${DUCKLAKE_DATA_PATH}": st.text_input("S3 data path", placeholder="s3://bucket/lake/"),
        "${DUCKLAKE_METADATA_SCHEMA}": st.text_input("PostgreSQL metadata schema", value="ducklake"),
        "${DUCKLAKE_CATALOG_NAME}": st.text_input("DuckDB catalog name", value="lake"),
    }
