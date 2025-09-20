import textwrap
import streamlit as st

from mlox.infra import Infrastructure, Bundle
from mlox.services.Kafka.docker import KafkaDockerService
from mlox.services.utils_ui import save_to_secret_store


def settings(infra: Infrastructure, bundle: Bundle, service: KafkaDockerService):
    st.write(f"Bootstrap server: {service.service_url}")
    st.write(f"SSL port: {service.service_ports.get('Kafka SSL')}")

    save_to_secret_store(
        infra,
        f"MLOX_KAFKA_{service.name.upper()}",
        {
            "bootstrap_server": service.service_url,
            "ssl_port": service.service_ports.get("Kafka SSL"),
            "certificate": service.certificate,
        },
    )

    st.code(
        textwrap.dedent(
            f"""
            from kafka import KafkaProducer, KafkaConsumer

            bootstrap = "{bundle.server.ip}:{service.service_ports.get('Kafka SSL')}"
            cafile_path = "./kafka-ca.pem"

            # Producer example
            producer = KafkaProducer(
                bootstrap_servers=[bootstrap],
                security_protocol="SSL",
                ssl_cafile=cafile_path,
                ssl_check_hostname=False,
            )
            producer.send("demo-topic", b"hello from mlox")
            producer.flush()
            producer.close()

            # Consumer example
            consumer = KafkaConsumer(
                "demo-topic",
                bootstrap_servers=[bootstrap],
                security_protocol="SSL",
                ssl_cafile=cafile_path,
                ssl_check_hostname=False,
                auto_offset_reset="earliest",
                enable_auto_commit=False,
            )
            for message in consumer:
                print(message.value)
                break
            consumer.close()
            """
        ).strip(),
        language="python",
        line_numbers=True,
    )

    if service.certificate:
        st.markdown("#### TLS certificate")
        st.code(service.certificate.strip(), language="bash")
