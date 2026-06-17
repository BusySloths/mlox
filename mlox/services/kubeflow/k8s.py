import json
import logging
import secrets
import shlex
from dataclasses import dataclass
from typing import Dict

from mlox.executors import TaskGroup
from mlox.service import AbstractService, ServiceCapability

logger = logging.getLogger(__name__)


@dataclass
class KubeflowService(AbstractService):
    """Install the upstream Kubeflow manifests on a Kubernetes cluster."""

    capabilities = {ServiceCapability.DASHBOARD}
    version: str = "v1.10.1"
    kubeconfig: str = "/etc/rancher/k3s/k3s.yaml"
    ingress_namespace: str = "istio-system"
    ingress_name: str = "kubeflow"
    ingress_service: str = "istio-ingressgateway"
    ingress_port: int = 8443
    traefik_namespace: str = "kubeflow-traefik"
    traefik_release: str = "kubeflow-traefik"
    traefik_chart_version: str = "34.4.1"
    minio_image: str = (
        "docker.io/minio/minio:RELEASE.2019-08-14T20-37-41Z"
    )
    dex_email: str = "user@example.com"
    dex_password: str = "12341234"
    install_attempts: int = 3
    webhook_ready_timeout_seconds: int = 120
    pipeline_ready_timeout_seconds: int = 300
    teardown_timeout_seconds: int = 120

    @property
    def manifests_url(self) -> str:
        return f"https://github.com/kubeflow/manifests/example?ref={self.version}"

    def setup(self, conn) -> None:
        logger.info("🔧 Installing Kubeflow %s", self.version)
        self.exec.fs_create_dir(conn, self.target_path)

        if not self._apply_kubeflow_manifests(conn):
            logger.error("Failed to apply the Kubeflow manifests.")
            self.state = "unknown"
            return

        if not self._repair_pipeline_storage(conn):
            logger.error("Failed to configure the Kubeflow Pipelines object store.")
            self.state = "unknown"
            return

        if not self._wait_for_pipeline_services(conn):
            logger.error("Kubeflow Pipelines did not become ready.")
            self.state = "unknown"
            return

        if not self._refresh_authentication(conn):
            logger.error("Failed to synchronize Kubeflow authentication.")
            self.state = "unknown"
            return

        if not self._configure_jupyter_cookies(conn):
            logger.error("Failed to configure secure Kubeflow Jupyter cookies.")
            self.state = "unknown"
            return

        self._remove_legacy_ingress_resources(conn)
        traefik_values_path = self._write_traefik_values(conn)
        if not self._install_dedicated_traefik(conn, traefik_values_path):
            logger.error("Failed to install the dedicated Kubeflow Traefik ingress.")
            self.state = "unknown"
            return

        self.service_ports["Kubeflow"] = self.ingress_port
        self.service_urls["Kubeflow"] = f"https://{conn.host}:{self.ingress_port}/"
        self.state = "running"

    def teardown(self, conn) -> None:
        logger.info("🗑️ Uninstalling Kubeflow")
        delete_args = [
            "--wait=false",
            f"--request-timeout={self.teardown_timeout_seconds}s",
        ]
        self._remove_legacy_ingress_resources(conn, extra_args=delete_args)
        self.exec.helm_uninstall(
            conn,
            release=self.traefik_release,
            namespace=self.traefik_namespace,
            kubeconfig=self.kubeconfig,
            extra_args=[f"--timeout={self.teardown_timeout_seconds}s"],
            ignore_missing=True,
        )
        self._run_kustomize(conn, "delete", ignore_not_found=True)
        self.exec.fs_delete_dir(conn, self.target_path)
        self.service_ports.clear()
        self.service_urls.clear()
        self.state = "un-initialized"

    def spin_up(self, conn) -> bool:
        return self.state == "running"

    def spin_down(self, conn) -> bool:
        logger.info("Kubeflow workloads are managed by Kubernetes.")
        return True

    def check(self, conn) -> Dict:
        command = self._kubectl_command(
            "-n",
            "kubeflow",
            "get",
            "deployment",
            "centraldashboard",
            "-o",
            "json",
        )
        result = self.exec.execute(
            conn,
            command,
            group=TaskGroup.KUBERNETES,
            sudo=True,
            description="Check the Kubeflow central dashboard",
        )
        if not result:
            return {
                "status": "unknown",
                "details": "Kubeflow central dashboard was not found.",
            }

        try:
            deployment = json.loads(result)
        except json.JSONDecodeError:
            return {
                "status": "unknown",
                "details": "Failed to parse the Kubeflow deployment status.",
            }

        desired = deployment.get("spec", {}).get("replicas", 1)
        available = deployment.get("status", {}).get("availableReplicas", 0)
        if desired > 0 and available >= desired:
            return {
                "status": "running",
                "details": "Kubeflow central dashboard is available.",
            }
        return {
            "status": "starting",
            "details": (
                f"Kubeflow central dashboard has {available}/{desired} "
                "available replicas."
            ),
        }

    def get_secrets(self) -> Dict[str, Dict]:
        return {
            "kubeflow_dex_credentials": {
                "email": self.dex_email,
                "password": self.dex_password,
                "service_url": self.service_urls.get("Kubeflow", ""),
            }
        }

    def _apply_kubeflow_manifests(self, conn) -> bool:
        # The upstream manifests contain CRDs and resources that depend on those
        # CRDs. Server-side apply avoids oversized last-applied annotations on
        # large CRDs, and retries handle API discovery propagation.
        for attempt in range(1, self.install_attempts + 1):
            result = self._run_kustomize(conn, "apply")
            if result is not None:
                return True
            if attempt < self.install_attempts:
                logger.warning(
                    "Kubeflow manifest apply attempt %s/%s failed; waiting "
                    "for admission webhooks before retrying.",
                    attempt,
                    self.install_attempts,
                )
                self._wait_for_admission_webhooks(conn)
        return False

    def _wait_for_admission_webhooks(self, conn) -> None:
        # A partial apply can register admission configurations before their
        # backing deployments have endpoints. Wait for all known blockers
        # before retrying the full manifest set.
        for namespace, deployment, description in (
            (
                "knative-serving",
                "deployment/webhook",
                "Wait for the Knative admission webhook",
            ),
            (
                "kubeflow",
                "deployment/kserve-controller-manager",
                "Wait for the KServe admission webhook",
            ),
        ):
            self._rollout_status(
                conn,
                namespace,
                deployment,
                description,
            )

    def _refresh_authentication(self, conn) -> bool:
        if not self._rollout_status(
            conn,
            "auth",
            "deployment/dex",
            "Wait for Dex",
        ):
            return False

        command = self._kubectl_command(
            "-n",
            "oauth2-proxy",
            "set",
            "env",
            "deployment/oauth2-proxy",
            f"OAUTH2_PROXY_COOKIE_SECRET={secrets.token_hex(16)}",
        )
        result = self.exec.execute(
            conn,
            command,
            group=TaskGroup.KUBERNETES,
            sudo=True,
            description="Rotate the OAuth2 Proxy session key",
        )
        if result is None:
            return False

        command = self._kubectl_command(
            "-n",
            "istio-system",
            "rollout",
            "restart",
            "deployment/istiod",
        )
        result = self.exec.execute(
            conn,
            command,
            group=TaskGroup.KUBERNETES,
            sudo=True,
            description="Restart deployment/istiod",
        )
        if result is None:
            return False

        return self._rollout_status(
            conn,
            "oauth2-proxy",
            "deployment/oauth2-proxy",
            "Wait for OAuth2 Proxy",
        ) and self._rollout_status(
            conn,
            "istio-system",
            "deployment/istiod",
            "Wait for Istio",
        )

    def _repair_pipeline_storage(self, conn) -> bool:
        command = self._kubectl_command(
            "-n",
            "kubeflow",
            "set",
            "image",
            "deployment/minio",
            f"minio={self.minio_image}",
        )
        result = self.exec.execute(
            conn,
            command,
            group=TaskGroup.KUBERNETES,
            sudo=True,
            description="Use the supported MinIO image for Kubeflow Pipelines",
        )
        return result is not None

    def _wait_for_pipeline_services(self, conn) -> bool:
        for resource, description in (
            ("deployment/mysql", "Wait for the Kubeflow Pipelines database"),
            ("deployment/minio", "Wait for the Kubeflow Pipelines object store"),
            ("deployment/ml-pipeline", "Wait for the Kubeflow Pipelines API"),
            ("deployment/ml-pipeline-ui", "Wait for the Kubeflow Pipelines UI"),
        ):
            if not self._rollout_status(
                conn,
                "kubeflow",
                resource,
                description,
                timeout_seconds=self.pipeline_ready_timeout_seconds,
            ):
                return False
        return True

    def _rollout_status(
        self,
        conn,
        namespace: str,
        resource: str,
        description: str,
        *,
        timeout_seconds: int | None = None,
    ) -> bool:
        timeout = timeout_seconds or self.webhook_ready_timeout_seconds
        command = self._kubectl_command(
            "-n",
            namespace,
            "rollout",
            "status",
            resource,
            f"--timeout={timeout}s",
        )
        result = self.exec.execute(
            conn,
            command,
            group=TaskGroup.KUBERNETES,
            sudo=True,
            description=description,
        )
        return result is not None

    def _configure_jupyter_cookies(self, conn) -> bool:
        command = self._kubectl_command(
            "-n",
            "kubeflow",
            "set",
            "env",
            "deployment/jupyter-web-app-deployment",
            "APP_SECURE_COOKIES=true",
        )
        result = self.exec.execute(
            conn,
            command,
            group=TaskGroup.KUBERNETES,
            sudo=True,
            description="Configure secure Jupyter cookies",
        )
        return result is not None

    def _run_kustomize(
        self,
        conn,
        action: str,
        *,
        ignore_not_found: bool = False,
    ) -> str | None:
        args = [action]
        if action == "apply":
            args.extend(["--server-side", "--force-conflicts"])
        elif action == "delete":
            args.extend(
                [
                    "--wait=false",
                    f"--request-timeout={self.teardown_timeout_seconds}s",
                ]
            )
        args.extend(["-k", self.manifests_url])
        if ignore_not_found:
            args.append("--ignore-not-found")
        command = self._kubectl_command(*args)
        if action == "delete":
            command = shlex.join(
                [
                    "timeout",
                    "--signal=TERM",
                    "--kill-after=10s",
                    f"{self.teardown_timeout_seconds}s",
                ]
            ) + f" {command}"
        return self.exec.execute(
            conn,
            command,
            group=TaskGroup.KUBERNETES,
            sudo=True,
            description=f"{action.title()} Kubeflow manifests",
        )

    def _kubectl_command(self, *args: str) -> str:
        return shlex.join(["kubectl", "--kubeconfig", self.kubeconfig, *args])

    def _remove_legacy_ingress_resources(
        self,
        conn,
        *,
        extra_args: list[str] | None = None,
    ) -> None:
        delete_args = extra_args or [
            "--wait=false",
            f"--request-timeout={self.teardown_timeout_seconds}s",
        ]
        for resource_type, name in (
            ("ingress", self.ingress_name),
            ("ingress", f"{self.ingress_name}-entry"),
            ("ingress", f"{self.ingress_name}-routes"),
            ("middleware", f"{self.ingress_name}-auth-redirect"),
            ("middleware", f"{self.ingress_name}-strip-prefix"),
        ):
            self.exec.k8s_delete_resource(
                conn,
                resource_type,
                name,
                namespace=self.ingress_namespace,
                kubeconfig=self.kubeconfig,
                extra_args=delete_args,
            )

    def _write_traefik_values(self, conn) -> str:
        values_path = f"{self.target_path}/kubeflow-traefik-values.yaml"
        values = f"""ingressClass:
  enabled: false
gateway:
  enabled: false
providers:
  kubernetesCRD:
    enabled: false
  kubernetesIngress:
    enabled: false
  file:
    enabled: true
    content: |-
      http:
        routers:
          kubeflow:
            entryPoints:
              - websecure
            rule: PathPrefix(`/`)
            service: kubeflow
            tls: {{}}
        services:
          kubeflow:
            loadBalancer:
              servers:
                - url: http://{self.ingress_service}.{self.ingress_namespace}.svc.cluster.local:80
ports:
  web:
    expose:
      default: false
  websecure:
    port: {self.ingress_port}
    exposedPort: {self.ingress_port}
    expose:
      default: true
service:
  type: LoadBalancer
"""
        self.exec.fs_write_file(conn, values_path, values)
        return values_path

    def _install_dedicated_traefik(self, conn, values_path: str) -> bool:
        repo_result = self.exec.helm_repo_add(
            conn,
            "kubeflow-traefik",
            "https://traefik.github.io/charts",
            kubeconfig=self.kubeconfig,
        )
        if repo_result is None:
            return False

        result = self.exec.helm_upgrade_install(
            conn,
            release=self.traefik_release,
            chart="kubeflow-traefik/traefik",
            namespace=self.traefik_namespace,
            kubeconfig=self.kubeconfig,
            create_namespace=True,
            extra_args=[
                "--version",
                self.traefik_chart_version,
                "-f",
                values_path,
                "--wait",
                "--timeout",
                "5m",
            ],
        )
        return result is not None
