from __future__ import annotations

from typing import Dict, List, Optional

import streamlit as st

from mlox.infra import Bundle, Infrastructure
from mlox.services.feast.docker import FeastDockerService
from mlox.services.postgres.docker import PostgresDockerService
from mlox.services.redis.docker import RedisDockerService


def _format_service_label(service, infra: Infrastructure) -> str:
    bundle = infra.get_bundle_by_service(service)
    host = bundle.server.ip if bundle else "?"
    return f"{service.name} ({host})"


def setup(infra: Infrastructure, bundle: Bundle) -> Dict | None:
    params: Dict[str, str] = {}
    st.write("Feast")
    st.caption(
        "Only the registry container is deployed here; the online (Redis) and offline"
        " (Postgres) stores are reused from existing services."
    )

    project_name = st.text_input("Feast project name", value="feast_project")
    params["${FEAST_PROJECT_NAME}"] = project_name

    redis_services: List[RedisDockerService] = [
        service
        for service in infra.filter_by_group("database")
        if isinstance(service, RedisDockerService)
    ]
    postgres_services: List[PostgresDockerService] = [
        service
        for service in infra.filter_by_group("database")
        if isinstance(service, PostgresDockerService)
    ]

    if not redis_services:
        st.warning("No Redis services available. Please deploy one before Feast.")
    if not postgres_services:
        st.warning("No Postgres services available. Please deploy one before Feast.")

    selected_redis: Optional[RedisDockerService] = None
    selected_postgres: Optional[PostgresDockerService] = None

    if redis_services:
        selected_redis = st.selectbox(
            "Online store (Redis)",
            options=redis_services,
            format_func=lambda svc: _format_service_label(svc, infra),
        )
    if postgres_services:
        selected_postgres = st.selectbox(
            "Offline store (Postgres)",
            options=postgres_services,
            format_func=lambda svc: _format_service_label(svc, infra),
        )

    if selected_redis is None or selected_postgres is None:
        return None

    params["${ONLINE_STORE_UUID}"] = selected_redis.uuid
    params["${OFFLINE_STORE_UUID}"] = selected_postgres.uuid

    return params


def settings(infra: Infrastructure, bundle: Bundle, service: FeastDockerService):
    st.header(f"Settings for service {service.name}")
    st.write(f"Registry URL: {service.service_urls.get('Feast Registry', 'n/a')}")
    st.write(f"Project name: {service.project_name}")

    redis = infra.get_service_by_uuid(service.online_store_uuid)
    postgres = infra.get_service_by_uuid(service.offline_store_uuid)

    if redis:
        redis_bundle = infra.get_bundle_by_service(redis)
        host = redis_bundle.server.ip if redis_bundle else ""
        port = redis.service_ports.get("Redis")
        host_display = host or "?"
        if port:
            host_display = f"{host_display}:{port}"
        st.write(f"Online store: {redis.name} ({host_display})")
    else:
        st.write("Online store: not linked")

    if postgres:
        postgres_bundle = infra.get_bundle_by_service(postgres)
        host = postgres_bundle.server.ip if postgres_bundle else ""
        port = postgres.service_ports.get("Postgres")
        host_display = host or "?"
        if port:
            host_display = f"{host_display}:{port}"
        st.write(f"Offline store: {postgres.name} ({host_display})")
    else:
        st.write("Offline store: not linked")
