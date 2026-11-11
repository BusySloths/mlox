"""Streamlit setup for the DuckLake connector."""
import streamlit as st

from mlox.service import ServiceCapability
from mlox.tui.services.setup import _ducklake_params


def setup(infra, bundle):
    postgres = [s for s in infra.services() if str(getattr(s, "service_config_id", "")).startswith("postgres-")]
    storage = [s for s in infra.services() if ServiceCapability.S3_OBJECT_STORAGE in getattr(s, "capabilities", set())]
    if not postgres or not storage:
        st.error("DuckLake requires PostgreSQL and S3-compatible object storage.")
        return None
    pg = st.selectbox("PostgreSQL service", postgres, format_func=lambda service: service.name)
    s3 = st.selectbox("Object storage service", storage, format_func=lambda service: service.name)
    name = st.text_input("Lake name", placeholder="sales")
    bucket = st.text_input("Existing S3 bucket")
    if not name or not bucket:
        return None
    try:
        return _ducklake_params({"lake_name": name, "bucket": bucket, "postgres_service_uuid": pg.uuid,
                                 "storage_service_uuid": s3.uuid}, infra)
    except ValueError as exc:
        st.error(str(exc))
        return None
