import json
import logging
import shlex
import textwrap
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
        self.namespace = f"mlflow-gateway-{self.port}"
        self.manifest_path = f"{self.target_path}/mlflow-gateway.yaml"
        self.traefik_values_path = f"{self.target_path}/traefik-values.yaml"

    @staticmethod
    def _yaml_string(value: str) -> str:
        return json.dumps(value)

    @staticmethod
    def _config_map_block(value: str) -> str:
        return textwrap.indent(value.rstrip(), "    ")

    def _render_gateway_manifest(self) -> str:
        serve_script = Path(self.serve_script).read_text(encoding="utf-8")
        requirements = _resolved_text(self.requirements_txt)
        cache_size = _resolved_setting(self.cache_max_models, "10")
        cache_ttl = _resolved_setting(self.cache_ttl_days, "10")

        return f"""apiVersion: v1
kind: Namespace
metadata:
  name: {self.namespace}
---
apiVersion: v1
kind: ConfigMap
metadata:
  name: mlflow-gateway-code
  namespace: {self.namespace}
data:
  serve.py: |-
{self._config_map_block(serve_script)}
  gateway-requirements.txt: |-
{self._config_map_block(requirements)}
---
apiVersion: v1
kind: Secret
metadata:
  name: mlflow-gateway-credentials
  namespace: {self.namespace}
type: Opaque
stringData:
  gateway-user: {self._yaml_string(self.user)}
  gateway-password: {self._yaml_string(self.pw)}
  tracking-uri: {self._yaml_string(self.tracking_uri)}
  tracking-user: {self._yaml_string(self.tracking_user)}
  tracking-password: {self._yaml_string(self.tracking_pw)}
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
      app.kubernetes.io/name: mlflow-gateway
  template:
    metadata:
      labels:
        app.kubernetes.io/name: mlflow-gateway
    spec:
      containers:
        - name: gateway
          image: python:3.12-slim
          imagePullPolicy: IfNotPresent
          workingDir: /app
          command: ["/bin/bash", "-lc"]
          args:
            - |
              set -euo pipefail
              pip install --no-cache-dir \
                "mlflow==3.8.1" \
                "mlflow[extras]==3.8.1" \
                "fastapi==0.115.0" \
                "uvicorn[standard]==0.30.6" \
                "pandas>=2.2" \
                "numpy>=1.26"
              if [ -s /app/gateway-requirements.txt ]; then
                pip install --no-cache-dir -r /app/gateway-requirements.txt
              fi
              exec uvicorn serve:app --host 0.0.0.0 --port {self.container_port}
          env:
            - name: MLFLOW_URI
              valueFrom:
                secretKeyRef:
                  name: mlflow-gateway-credentials
                  key: tracking-uri
            - name: MLFLOW_TRACKING_URI
              valueFrom:
                secretKeyRef:
                  name: mlflow-gateway-credentials
                  key: tracking-uri
            - name: MLFLOW_TRACKING_USERNAME
              valueFrom:
                secretKeyRef:
                  name: mlflow-gateway-credentials
                  key: tracking-user
            - name: MLFLOW_TRACKING_PASSWORD
              valueFrom:
                secretKeyRef:
                  name: mlflow-gateway-credentials
                  key: tracking-password
            - name: MLFLOW_TRACKING_INSECURE_TLS
              value: "true"
            - name: MLOX_GATEWAY_CACHE_MAX_MODELS
              value: {self._yaml_string(cache_size)}
            - name: MLOX_GATEWAY_CACHE_TTL_DAYS
              value: {self._yaml_string(cache_ttl)}
          ports:
            - name: http
              containerPort: {self.container_port}
          startupProbe:
            httpGet:
              path: /health
              port: http
            periodSeconds: 5
            failureThreshold: 120
          readinessProbe:
            httpGet:
              path: /health
              port: http
            periodSeconds: 5
            failureThreshold: 6
          livenessProbe:
            httpGet:
              path: /health
              port: http
            periodSeconds: 10
            failureThreshold: 6
          volumeMounts:
            - name: gateway-code
              mountPath: /app/serve.py
              subPath: serve.py
              readOnly: true
            - name: gateway-code
              mountPath: /app/gateway-requirements.txt
              subPath: gateway-requirements.txt
              readOnly: true
      volumes:
        - name: gateway-code
          configMap:
            name: mlflow-gateway-code
---
apiVersion: v1
kind: Service
metadata:
  name: {self.service_name}
  namespace: {self.namespace}
spec:
  type: ClusterIP
  selector:
    app.kubernetes.io/name: mlflow-gateway
  ports:
    - name: http
      port: {self.container_port}
      targetPort: http
"""

    def _render_traefik_values(self) -> str:
        password_hash = apr_md5_crypt.hash(self.pw)
        auth_user = self._yaml_string(f"{self.user}:{password_hash}")
        backend_url = (
            f"http://{self.service_name}.{self.namespace}.svc.cluster.local:"
            f"{self.container_port}"
        )

        return f"""deployment:
  replicas: 1
ingressClass:
  enabled: false
providers:
  kubernetesCRD:
    enabled: false
  kubernetesIngress:
    enabled: false
  file:
    enabled: true
    watch: true
    content: |-
      http:
        routers:
          gateway:
            entryPoints:
              - websecure
            rule: PathPrefix(`/`)
            service: gateway
            middlewares:
              - gateway-auth
            tls: {{}}
        middlewares:
          gateway-auth:
            basicAuth:
              users:
                - {auth_user}
        services:
          gateway:
            loadBalancer:
              servers:
                - url: {self._yaml_string(backend_url)}
ports:
  web:
    expose:
      default: false
  websecure:
    port: 8443
    exposedPort: {self.port}
    expose:
      default: true
service:
  type: LoadBalancer
"""

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
            logger.error("MLflow Gateway deployment did not become ready.")
            self.state = "unknown"
            return

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
            self.state = "unknown"
            return {"status": "unknown", "ready_replicas": (ready or "0").strip()}

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
