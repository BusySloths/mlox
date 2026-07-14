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
    ingress_port: int = 443
    rollout_timeout_seconds: int = 600
    teardown_timeout_seconds: int = 120
    gateway_id: str = field(init=False)
    namespace: str = field(init=False)
    deployment_name: str = field(init=False, default="mlflow-gateway")
    service_name: str = field(init=False, default="mlflow-gateway")
    ingress_name: str = field(init=False, default="mlflow-gateway")
    ingress_path: str = field(init=False)
    basic_auth_secret: str = field(init=False, default="mlflow-gateway-basic-auth")
    basic_auth_middleware: str = field(init=False, default="mlflow-gateway-auth")
    strip_prefix_middleware: str = field(
        init=False, default="mlflow-gateway-strip-prefix"
    )
    manifest_path: str = field(init=False)

    def __post_init__(self) -> None:
        super().__post_init__()
        self.gateway_id = self._gateway_id()
        self.namespace = f"mlflow-gateway-{self.gateway_id}"
        self.ingress_path = f"/gateway-{self.gateway_id}"
        self.manifest_path = f"{self.target_path}/mlflow-gateway.yaml"

    def _gateway_id(self) -> str:
        return re.sub(r"[^a-z0-9-]", "-", self.uuid[:8].lower()).strip("-")

    def _render_gateway_manifest(self) -> str:
        serve_script = Path(self.serve_script).read_text(encoding="utf-8")
        requirements = _resolved_text(self.requirements_txt)
        cache_size = _resolved_setting(self.cache_max_models, "10")
        cache_ttl = _resolved_setting(self.cache_ttl_days, "10")
        password_hash = apr_md5_crypt.hash(self.pw)

        return self.render_template(
            "gateway-manifest.yaml.tmpl",
            {
                "namespace": self.namespace,
                "serve_script_block": self.indent_block(serve_script, 4),
                "requirements_block": self.indent_block(requirements, 4),
                "gateway_user": self.yaml_scalar(self.user),
                "gateway_password": self.yaml_scalar(self.pw),
                "basic_auth_secret": self.basic_auth_secret,
                "basic_auth_user": self.yaml_scalar(f"{self.user}:{password_hash}"),
                "basic_auth_middleware": self.basic_auth_middleware,
                "strip_prefix_middleware": self.strip_prefix_middleware,
                "ingress_name": self.ingress_name,
                "ingress_path": self.yaml_scalar(self.ingress_path),
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

    def _kubectl(self, arguments: str) -> str:
        return f"kubectl --kubeconfig {shlex.quote(self.kubeconfig)} {arguments}"

    def setup(self, conn) -> None:
        self.exec.fs_create_dir(conn, self.target_path)
        self.exec.fs_write_file(
            conn, self.manifest_path, self._render_gateway_manifest()
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

        self.service_url = f"https://{conn.host}{self.ingress_path}"
        self.service_urls["MLflow Gateway REST API"] = self.service_url
        self.service_ports["MLflow Gateway REST API"] = self.ingress_port
        self.state = "running"

    def spin_up(self, conn) -> bool:
        return True

    def spin_down(self, conn) -> bool:
        return True

    def log_labels(self) -> list[str]:
        return ["MLflow Gateway"]

    def service_log_tail(self, conn, label: str | None = None, tail: int = 200) -> str:
        if label and label not in self.log_labels():
            return f"Log label {label} not found"
        return self.exec.k8s_resource_log_tail(
            conn,
            f"deployment/{self.deployment_name}",
            namespace=self.namespace,
            tail=tail,
            kubeconfig=self.kubeconfig,
            container="gateway",
        )

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
