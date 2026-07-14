import logging
import re
import shlex
from dataclasses import dataclass, field
from pathlib import Path

from passlib.hash import apr_md5_crypt

from mlox.executors import TaskGroup
from mlox.services.mlflow_gateway.docker import (
    MLFlowGatewayDockerService,
    _resolved_setting,
    _resolved_text,
)

logger = logging.getLogger(__name__)


@dataclass
class MLFlowGatewayK3sService(MLFlowGatewayDockerService):
    kubeconfig: str = "/etc/rancher/k3s/k3s.yaml"
    container_port: int = 8080
    rollout_timeout_seconds: int = 600
    teardown_timeout_seconds: int = 120
    traefik_chart_version: str = "34.4.1"
    namespace: str = field(init=False)
    deployment_name: str = field(init=False, default="mlflow-gateway")
    service_name: str = field(init=False, default="mlflow-gateway")
    traefik_release: str = field(init=False, default="mlflow-gateway-traefik")
    manifest_path: str = field(init=False)
    traefik_values_path: str = field(init=False)

    def __post_init__(self) -> None:
        super().__post_init__()
        suffix = self._resource_suffix()
        self.namespace = f"mlflow-gateway-{suffix}"
        self.traefik_release = f"mlflow-gateway-traefik-{suffix}"[:63].rstrip("-")
        self.manifest_path = f"{self.target_path}/mlflow-gateway.yaml"
        self.traefik_values_path = f"{self.target_path}/traefik-values.yaml"

    def _resource_suffix(self) -> str:
        port = re.sub(r"[^a-z0-9-]", "-", str(self.port).lower()).strip("-")
        unique = re.sub(r"[^a-z0-9-]", "-", self.uuid[:8].lower()).strip("-")
        return f"{port}-{unique}" if port else unique

    def _render_gateway_manifest(self) -> str:
        serve_script = Path(self.serve_script).read_text(encoding="utf-8")
        requirements = _resolved_text(self.requirements_txt)
        cache_size = _resolved_setting(self.cache_max_models, "10")
        cache_ttl = _resolved_setting(self.cache_ttl_days, "10")

        return self.render_template(
            "gateway-manifest.yaml.tmpl",
            {
                "namespace": self.namespace,
                "serve_script_block": self.indent_block(serve_script, 4),
                "requirements_block": self.indent_block(requirements, 4),
                "gateway_user": self.yaml_scalar(self.user),
                "gateway_password": self.yaml_scalar(self.pw),
                "tracking_uri": self.yaml_scalar(self.tracking_uri),
                "tracking_user": self.yaml_scalar(self.tracking_user),
                "tracking_password": self.yaml_scalar(self.tracking_pw),
                "deployment_name": self.deployment_name,
                "container_port": self.container_port,
                "cache_size": self.yaml_scalar(cache_size),
                "cache_ttl": self.yaml_scalar(cache_ttl),
                "service_name": self.service_name,
            },
        )

    def _render_traefik_values(self) -> str:
        password_hash = apr_md5_crypt.hash(self.pw)
        auth_user = self.yaml_scalar(f"{self.user}:{password_hash}")
        backend_url = (
            f"http://{self.service_name}.{self.namespace}.svc.cluster.local:"
            f"{self.container_port}"
        )

        return self.render_template(
            "traefik-values.yaml.tmpl",
            {
                "auth_user": auth_user,
                "backend_url": self.yaml_scalar(backend_url),
                "port": self.port,
            },
        )

    def _kubectl(self, arguments: str) -> str:
        return f"kubectl --kubeconfig {shlex.quote(self.kubeconfig)} {arguments}"

    def setup(self, conn) -> None:
        self.exec.fs_create_dir(conn, self.target_path)
        self.exec.fs_write_file(
            conn, self.manifest_path, self._render_gateway_manifest()
        )
        self.exec.fs_write_file(
            conn, self.traefik_values_path, self._render_traefik_values()
        )

        if (
            self.exec.k8s_apply_manifest(
                conn, self.manifest_path, kubeconfig=self.kubeconfig
            )
            is None
        ):
            logger.error("Failed to apply the MLflow Gateway Kubernetes manifest.")
            self.state = "unknown"
            return

        rollout = self.exec.execute(
            conn,
            self._kubectl(
                f"rollout status deployment/{self.deployment_name} "
                f"--namespace {self.namespace} "
                f"--timeout={self.rollout_timeout_seconds}s"
            ),
            group=TaskGroup.KUBERNETES,
            sudo=True,
            description="Wait for the MLflow Gateway deployment",
        )
        if rollout is None:
            logger.warning(
                "MLflow Gateway deployment is still starting after %s seconds.",
                self.rollout_timeout_seconds,
            )

        if (
            self.exec.helm_repo_add(
                conn,
                "mlflow-gateway-traefik",
                "https://traefik.github.io/charts",
                kubeconfig=self.kubeconfig,
            )
            is None
        ):
            logger.error("Failed to add the Traefik Helm repository.")
            self.state = "unknown"
            return
        if (
            self.exec.helm_upgrade_install(
                conn,
                release=self.traefik_release,
                chart="mlflow-gateway-traefik/traefik",
                namespace=self.namespace,
                kubeconfig=self.kubeconfig,
                extra_args=[
                    "--version",
                    self.traefik_chart_version,
                    "--values",
                    self.traefik_values_path,
                    "--wait",
                    "--timeout",
                    "5m",
                ],
            )
            is None
        ):
            logger.error("Failed to install the MLflow Gateway Traefik release.")
            self.state = "unknown"
            return

        self.service_url = f"https://{conn.host}:{self.port}"
        self.service_urls["MLflow Gateway REST API"] = self.service_url
        self.service_ports["MLflow Gateway REST API"] = int(self.port)
        self.state = "running"

    def spin_up(self, conn) -> bool:
        return True

    def spin_down(self, conn) -> bool:
        return True

    def check(self, conn) -> dict:
        ready = self.exec.execute(
            conn,
            self._kubectl(
                f"get deployment/{self.deployment_name} "
                f"--namespace {self.namespace} "
                "-o jsonpath='{.status.readyReplicas}'"
            ),
            group=TaskGroup.KUBERNETES,
            sudo=True,
            description="Check MLflow Gateway deployment readiness",
        )
        if ready is None or ready.strip() != "1":
            self.state = "running"
            return {"status": "starting", "ready_replicas": (ready or "0").strip()}

        status = self.exec.execute(
            conn,
            "curl --silent --show-error --insecure "
            "--output /dev/null --write-out '%{http_code}' "
            f"--user {shlex.quote(f'{self.user}:{self.pw}')} "
            f"{shlex.quote(f'{self.service_url}/health')}",
            group=TaskGroup.NETWORKING,
            description="Check MLflow Gateway health",
        )
        if status is not None and status.strip() == "200":
            self.state = "running"
            return {"status": "running"}
        self.state = "unknown"
        return {"status": "unknown", "http_code": (status or "").strip()}

    def teardown(self, conn) -> None:
        self.exec.helm_uninstall(
            conn,
            release=self.traefik_release,
            namespace=self.namespace,
            kubeconfig=self.kubeconfig,
            ignore_missing=True,
            extra_args=[f"--timeout={self.teardown_timeout_seconds}s"],
        )
        self.exec.k8s_delete_resource(
            conn,
            "namespace",
            self.namespace,
            kubeconfig=self.kubeconfig,
            ignore_not_found=True,
            extra_args=[
                "--wait=false",
                f"--request-timeout={self.teardown_timeout_seconds}s",
            ],
        )
        self.exec.fs_delete_dir(conn, self.target_path)

        self.service_url = ""
        self.service_urls.clear()
        self.service_ports.clear()
        self.state = "un-initialized"
