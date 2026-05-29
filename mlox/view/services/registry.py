import os

import streamlit as st
import requests

from contextlib import contextmanager
from dataclasses import dataclass
from tempfile import NamedTemporaryFile
from typing import Iterator

from requests import Session

from mlox.infra import Bundle, Infrastructure
from mlox.services.registry.docker import RegistryDockerService
from mlox.view.services.common import save_to_secret_store


@dataclass
class RegistryImage:
    repository: str
    tags: list[str]

    @property
    def display_tags(self) -> str:
        return ", ".join(self.tags) if self.tags else "-"


def settings(infra: Infrastructure, bundle: Bundle, service: RegistryDockerService):
    registry_url = service.service_urls.get("Registry", "")

    tab_overview, tab_images, tab_tls = st.tabs(["Overview", "Images", "TLS"])

    with tab_overview:
        _render_overview(infra, service, registry_url)

    with tab_images:
        _render_images(service, registry_url)

    with tab_tls:
        _render_tls(service)


def _render_overview(
    infra: Infrastructure,
    service: RegistryDockerService,
    registry_url: str,
) -> None:
    st.write(f"Registry URL: {registry_url}")
    st.write(f"Username: {service.username}")
    st.write(f'Password: "{service.password}"')

    save_to_secret_store(
        infra,
        f"MLOX_REGISTRY_{service.name.upper()}",
        service.get_secrets().get("registry_credentials", {}),
    )

    if registry_url:
        st.code(
            f"docker login {registry_url} --username {service.username}",
            language="bash",
        )


def _render_images(service: RegistryDockerService, registry_url: str) -> None:
    if not registry_url:
        st.info("Registry URL is not available yet.")
        return

    if st.button(
        "Refresh images",
        key=f"refresh-registry-images-{service.uuid}",
        icon=":material/refresh:",
    ):
        _cached_list_registry_images.clear()

    try:
        images = _cached_list_registry_images(
            registry_url,
            service.username,
            service.password,
            service.certificate,
        )
    except requests.RequestException as exc:
        st.error(f"Could not load registry images: {exc}")
        return
    except ValueError as exc:
        st.error(f"Could not parse registry response: {exc}")
        return

    if not images:
        st.info("No images found in this registry.")
        return

    st.dataframe(
        [
            {
                "Repository": image.repository,
                "Tags": image.display_tags,
                "Tag count": len(image.tags),
            }
            for image in images
        ],
        width="stretch",
        hide_index=True,
        column_config={
            "Repository": st.column_config.TextColumn("Repository"),
            "Tags": st.column_config.TextColumn("Tags"),
            "Tag count": st.column_config.NumberColumn("Tag count"),
        },
    )


def _render_tls(service: RegistryDockerService) -> None:
    if service.certificate:
        st.markdown("#### TLS certificate")
        st.code(service.certificate.strip(), language="bash")
    else:
        st.info("No TLS certificate is available yet.")


@st.cache_data(ttl=30, show_spinner=False)
def _cached_list_registry_images(
    registry_url: str,
    username: str,
    password: str,
    certificate: str | None,
) -> list[RegistryImage]:
    return list_registry_images(
        registry_url=registry_url,
        username=username,
        password=password,
        certificate=certificate,
    )


def list_registry_images(
    *,
    registry_url: str,
    username: str,
    password: str,
    certificate: str | None = None,
) -> list[RegistryImage]:
    with _registry_session(username, password, certificate) as session:
        catalog_response = session.get(f"{registry_url}/v2/_catalog", timeout=20)
        catalog_response.raise_for_status()
        repositories = catalog_response.json().get("repositories", [])
        if not isinstance(repositories, list):
            raise ValueError("Registry catalog did not contain a repository list.")

        images: list[RegistryImage] = []
        for repository in repositories:
            if not isinstance(repository, str):
                continue
            tags_response = session.get(
                f"{registry_url}/v2/{repository}/tags/list",
                timeout=20,
            )
            tags_response.raise_for_status()
            tags = tags_response.json().get("tags") or []
            if not isinstance(tags, list):
                tags = []
            images.append(
                RegistryImage(
                    repository=repository,
                    tags=sorted(tag for tag in tags if isinstance(tag, str)),
                )
            )

        return sorted(images, key=lambda image: image.repository)


@contextmanager
def _registry_session(
    username: str,
    password: str,
    certificate: str | None,
) -> Iterator[Session]:
    session = requests.Session()
    session.auth = (username, password)

    cert_file = None
    try:
        if certificate:
            cert_file = NamedTemporaryFile(mode="w", delete=False)
            cert_file.write(certificate)
            cert_file.flush()
            session.verify = cert_file.name
        else:
            session.verify = False

        yield session
    finally:
        session.close()
        if cert_file is not None:
            cert_path = cert_file.name
            cert_file.close()
            try:
                os.unlink(cert_path)
            except OSError:
                pass
