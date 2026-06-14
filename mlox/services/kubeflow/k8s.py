import json
import logging
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
    ingress_port: int = 80
    install_attempts: int = 3

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

        ingress_path = self._write_ingress_manifest(conn)
        result = self.exec.k8s_apply_manifest(
            conn,
            ingress_path,
            namespace=self.ingress_namespace,
            kubeconfig=self.kubeconfig,
        )
        if result is None:
            logger.error("Failed to configure the Kubeflow Traefik ingress.")
            self.state = "unknown"
            return

        self.service_ports["Kubeflow"] = self.ingress_port
        self.service_urls["Kubeflow"] = f"http://{conn.host}:{self.ingress_port}/"
        self.state = "running"

    def teardown(self, conn) -> None:
        logger.info("🗑️ Uninstalling Kubeflow")
        self.exec.k8s_delete_resource(
            conn,
            "ingress",
            self.ingress_name,
            namespace=self.ingress_namespace,
            kubeconfig=self.kubeconfig,
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
        return {}

    def _apply_kubeflow_manifests(self, conn) -> bool:
        # The upstream manifests contain CRDs and resources that depend on those
        # CRDs. Retrying the idempotent apply handles API discovery propagation.
        for attempt in range(1, self.install_attempts + 1):
            result = self._run_kustomize(conn, "apply")
            if result is not None:
                return True
            logger.warning(
                "Kubeflow manifest apply attempt %s/%s failed; retrying.",
                attempt,
                self.install_attempts,
            )
        return False

    def _run_kustomize(
        self,
        conn,
        action: str,
        *,
        ignore_not_found: bool = False,
    ) -> str | None:
        args = [action, "-k", self.manifests_url]
        if ignore_not_found:
            args.append("--ignore-not-found")
        return self.exec.execute(
            conn,
            self._kubectl_command(*args),
            group=TaskGroup.KUBERNETES,
            sudo=True,
            description=f"{action.title()} Kubeflow manifests",
        )

    def _kubectl_command(self, *args: str) -> str:
        return shlex.join(["kubectl", "--kubeconfig", self.kubeconfig, *args])

    def _write_ingress_manifest(self, conn) -> str:
        manifest_path = f"{self.target_path}/{self.ingress_name}-ingress.yaml"
        manifest = f"""apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: {self.ingress_name}
  namespace: {self.ingress_namespace}
  annotations:
    kubernetes.io/ingress.class: traefik
    traefik.ingress.kubernetes.io/router.entrypoints: web
spec:
  ingressClassName: traefik
  rules:
    - http:
        paths:
          - path: /
            pathType: Prefix
            backend:
              service:
                name: {self.ingress_service}
                port:
                  number: 80
"""
        self.exec.fs_write_file(conn, manifest_path, manifest)
        return manifest_path
