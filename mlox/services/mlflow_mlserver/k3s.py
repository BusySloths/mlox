import logging
import shlex
import textwrap
import re

from dataclasses import dataclass, field
from typing import Dict

from mlox.executors import TaskGroup
from mlox.services.mlflow_mlserver.docker import MLFlowMLServerDockerService

logger = logging.getLogger(__name__)


@dataclass
class MLFlowMLServerK3sService(MLFlowMLServerDockerService):
    namespace: str = "mlserver"
    kubeconfig: str = "/etc/rancher/k3s/k3s.yaml"
    container_port: int = 5002
    deployment_name: str = field(default="", init=False)
    service_name: str = field(default="", init=False)
    manifest_path: str = field(default="", init=False)

    def __post_init__(self):
        super().__post_init__()
        safe_name = re.sub(r"[^a-z0-9-]", "-", self.name.lower()).strip("-")
        suffix = f"{safe_name}-{self.port}"
        self.deployment_name = f"mlflow-mlserver-{suffix}"[:63].rstrip("-")
        self.service_name = self.deployment_name
        self.manifest_path = f"{self.target_path}/{self.deployment_name}.yaml"

    def _render_manifest(self) -> str:
        model = self.model.replace("'", "''")
        tracking_uri = self.tracking_uri.replace("'", "''")
        tracking_user = self.tracking_user.replace("'", "''")
        tracking_pw = self.tracking_pw.replace("'", "''")

        startup_cmd = textwrap.dedent(
            """
            set -euo pipefail
            pip install --no-cache-dir "mlflow==3.8.1" "mlflow[extras]==3.8.1" "mlserver~=1.7.1" "mlserver-mlflow~=1.7.1" "uvloop==0.21.0"
            mlflow models serve -m models:/$MLFLOW_REMOTE_MODEL -p 5002 -h 0.0.0.0 -w 1 --enable-mlserver
            """
        ).strip()

        return f"""apiVersion: v1
kind: Namespace
metadata:
  name: {self.namespace}
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: {self.deployment_name}
  namespace: {self.namespace}
spec:
  replicas: 1
  selector:
    matchLabels:
      app: {self.service_name}
  template:
    metadata:
      labels:
        app: {self.service_name}
    spec:
      containers:
      - name: mlserver
        image: python:3.11-slim
        imagePullPolicy: IfNotPresent
        command: ["/bin/bash", "-lc"]
        args:
        - |
{textwrap.indent(startup_cmd, '          ')}
        ports:
        - containerPort: {self.container_port}
          name: http
        env:
        - name: MLFLOW_TRACKING_URI
          value: '{tracking_uri}'
        - name: MLFLOW_TRACKING_USERNAME
          value: '{tracking_user}'
        - name: MLFLOW_TRACKING_PASSWORD
          value: '{tracking_pw}'
        - name: MLFLOW_TRACKING_INSECURE_TLS
          value: "true"
        - name: MLFLOW_REMOTE_MODEL
          value: '{model}'
        readinessProbe:
          httpGet:
            path: /v2/health/ready
            port: {self.container_port}
          initialDelaySeconds: 20
          periodSeconds: 5
        livenessProbe:
          httpGet:
            path: /v2/health/live
            port: {self.container_port}
          initialDelaySeconds: 40
          periodSeconds: 10
---
apiVersion: v1
kind: Service
metadata:
  name: {self.service_name}
  namespace: {self.namespace}
spec:
  type: NodePort
  selector:
    app: {self.service_name}
  ports:
  - name: http
    port: {self.container_port}
    targetPort: {self.container_port}
    nodePort: {self.port}
"""

    def setup(self, conn) -> None:
        self.exec.fs_create_dir(conn, self.target_path)
        self.exec.fs_write_file(conn, self.manifest_path, self._render_manifest())
        self.exec.k8s_apply_manifest(
            conn,
            self.manifest_path,
            kubeconfig=self.kubeconfig,
        )

        self.service_ports["MLServer REST API"] = int(self.port)
        self.service_urls["MLServer REST API"] = f"http://{conn.host}:{self.port}"
        self.service_url = f"http://{conn.host}:{self.port}"

    def teardown(self, conn):
        self.exec.k8s_delete_manifest(
            conn,
            self.manifest_path,
            kubeconfig=self.kubeconfig,
            ignore_not_found=True,
        )
        self.exec.fs_delete_dir(conn, self.target_path)
        self.state = "stopped"

    def spin_up(self, conn) -> bool:
        logger.info("🔄 no spinning up needed for k3s manifests")
        return True

    def spin_down(self, conn) -> bool:
        logger.info("🔄 no spinning down needed for k3s manifests")
        return True

    def check(self, conn) -> Dict:
        try:
            command = (
                f"kubectl -n {self.namespace} get deployment {self.deployment_name} "
                "-o jsonpath='{.status.readyReplicas}'"
            )
            replicas = self.exec.execute(
                conn,
                command,
                group=TaskGroup.KUBERNETES,
                sudo=True,
            )
            if not replicas or replicas.strip() != "1":
                self.state = "unknown"
                return {"status": "unknown", "ready_replicas": (replicas or "0").strip()}

            health_url = shlex.quote(f"{self.service_url}/v2/health/ready")
            cmd = f"curl -s -o /dev/null -w '%{{http_code}}' {health_url}"
            code = self.exec.execute(
                conn,
                command=cmd,
                group=TaskGroup.NETWORKING,
                description="Check MLServer readiness",
            )
            if code and code.strip() == "200":
                self.state = "running"
                return {"status": "running"}
            self.state = "unknown"
            return {"status": "unknown", "http_code": (code or "").strip()}
        except Exception as exc:
            logger.error("Error checking k3s MLServer status: %s", exc)
            self.state = "unknown"
            return {"status": "unknown"}
