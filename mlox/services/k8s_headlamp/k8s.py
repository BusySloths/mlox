import logging
from typing import Dict
from dataclasses import dataclass, field

from mlox.executors import TaskGroup
from mlox.service import AbstractService

logger = logging.getLogger(__name__)


@dataclass
class K8sHeadlampService(AbstractService):
    namespace: str = "kube-system"
    service_name: str = "my-headlamp"
    kubeconfig: str = field(default="/etc/rancher/k3s/k3s.yaml", init=False)

    def get_login_token(self, bundle) -> str:
        token = "no token"
        if not bundle.server:
            logger.error("No server connection available")
            return token
        with bundle.server.get_server_connection() as conn:
            _token = self.exec.k8s_create_token(
                conn,
                service_account=self.service_name,
                namespace=self.namespace,
            )
            if _token:
                token = _token
        return token

    def setup(self, conn) -> None:
        logger.info("🔧 Installing K8s Headlamp")
        src_url = "https://kubernetes-sigs.github.io/headlamp/"

        # Add kubernetes-dashboard repository
        self.exec.helm_repo_add(
            conn,
            "headlamp",
            src_url,
            kubeconfig=self.kubeconfig,
        )
        # Deploy a Helm Release named "kubernetes-dashboard" using the kubernetes-dashboard chart
        self.exec.helm_upgrade_install(
            conn,
            release=self.service_name,
            chart="headlamp/headlamp",
            namespace=self.namespace,
            kubeconfig=self.kubeconfig,
            create_namespace=True,
        )
        self._bind_service_account_cluster_admin(conn)
        # Install Plugins
        # self.install_gadgets_plugin(conn)

        # Expose the Dashboard Service via Ingress or NodePort
        node_ip, port, path = self.expose_dashboard_ingress(conn)
        # node_ip, port = self.expose_dashboard_nodeport(conn)
        url_path = "" if path == "/" else path
        self.service_urls["Headlamp"] = f"https://{node_ip}:{port}{url_path}"
        self.service_ports["Headlamp"] = port
        self.state = "running"
        logger.info("✅ K8s Headlamp installation complete")

    def expose_dashboard_nodeport(
        self,
        conn,
        node_port=32001,
    ):
        """
        Converts the Dashboard Service to NodePort and returns (node_ip, node_port).
        """
        # 1) Patch the Service to add a name to the port, which is required.
        patch_body = {
            "spec": {
                "type": "NodePort",
                "ports": [
                    {
                        "name": "plain-http",
                        "port": 8080,
                        "targetPort": 4466,
                        "nodePort": node_port,
                    }
                ],
            }
        }
        self.exec.k8s_patch_resource(
            conn,
            "svc",
            self.service_name,
            patch_body,
            namespace=self.namespace,
        )
        node_ip = conn.host

        logger.info(f"Dashboard exposed at http://{node_ip}:{node_port}")
        return node_ip, node_port

    def expose_dashboard_ingress(
        self,
        conn,
        ingress_name: str | None = None,
        ingress_port: int = 443,
        backend_service_port: int | None = None,
        path_prefix: str | None = None,
        entrypoint: str = "websecure",
    ):
        """
        Expose Headlamp through the Traefik ingress and return (node_ip, ingress_port).
        """
        ingress_name = ingress_name or f"{self.service_name}-ingress"
        node_ip = conn.host
        backend_port = backend_service_port or self._detect_service_port(conn)
        path = self._normalize_path_prefix(path_prefix)
        middleware_name = f"{self.service_name}-strip-prefix" if path != "/" else None

        annotations_lines = [
            "    kubernetes.io/ingress.class: traefik",
            f"    traefik.ingress.kubernetes.io/router.entrypoints: {entrypoint}",
            '    traefik.ingress.kubernetes.io/router.tls: "true"',
        ]
        if middleware_name:
            annotations_lines.append(
                "    traefik.ingress.kubernetes.io/router.middlewares: "
                f"{self.namespace}-{middleware_name}@kubernetescrd"
            )
        annotations_block = "\n".join(annotations_lines)

        ingress_manifest = f"""apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: {ingress_name}
  namespace: {self.namespace}
  annotations:
{annotations_block}
spec:
  ingressClassName: traefik
  rules:
  - http:
      paths:
      - path: {path}
        pathType: ImplementationSpecific
        backend:
          service:
            name: {self.service_name}
            port:
              number: {backend_port}
"""
        middleware_manifest = ""
        if middleware_name:
            middleware_manifest = f"""---
apiVersion: traefik.containo.us/v1alpha1
kind: Middleware
metadata:
  name: {middleware_name}
  namespace: {self.namespace}
spec:
  stripPrefix:
    prefixes:
    - {path}
"""

        manifest_path = f"{self.target_path}/{ingress_name}.yaml"
        self.exec.fs_create_dir(conn, self.target_path)
        self.exec.fs_write_file(
            conn,
            manifest_path,
            f"{ingress_manifest}{middleware_manifest}",
        )
        self.exec.k8s_apply_manifest(
            conn,
            manifest_path,
            namespace=self.namespace,
        )

        logger.info(
            f"Dashboard exposed at https://{node_ip}:{ingress_port}{'' if path == '/' else path} via ingress"
        )
        return node_ip, ingress_port, path

    def install_gadgets_plugin(self, conn) -> None:
        """Install/upgrade Headlamp with the Gadgets plugin enabled via Helm values."""
        logger.info("🔧 Enabling Headlamp Gadgets plugin")
        values_path = f"{self.target_path}/plugin-gadgets-values.yaml"

        values_yaml = f"""initContainers:
  - name: headlamp-plugins
    image: ghcr.io/inspektor-gadget/headlamp-plugin:0.1.0-beta.2
    imagePullPolicy: Always
    command:
      [
        "/bin/sh",
        "-c",
        "mkdir -p /build/plugins && cp -r /plugins/* /build/plugins/",
      ]
    volumeMounts:
      - name: headlamp-plugins
        mountPath: /build/plugins

persistentVolumeClaim:
  enabled: true
  accessModes:
    - ReadWriteOnce
  size: 1Gi

volumeMounts:
  - name: headlamp-plugins
    mountPath: /build/plugins

volumes:
  - name: headlamp-plugins
    persistentVolumeClaim:
      claimName: "{self.service_name}"

config:
  pluginsDir: /build/plugins
"""
        self.exec.fs_create_dir(conn, self.target_path)
        self.exec.fs_write_file(conn, values_path, values_yaml)

        # Upgrade the existing release with the plugin values.
        self.exec.helm_upgrade_install(
            conn,
            release=self.service_name,
            chart="headlamp/headlamp",
            namespace=self.namespace,
            kubeconfig=self.kubeconfig,
            create_namespace=True,
            extra_args=["-f", values_path],
        )
        logger.info("✅ Gadgets plugin configuration applied")

    def _bind_service_account_cluster_admin(self, conn) -> None:
        """Grant Headlamp service account cluster-admin to enable log access."""
        binding_name = f"{self.service_name}-cluster-admin"
        manifest_path = f"{self.target_path}/{binding_name}.yaml"
        manifest = f"""apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRoleBinding
metadata:
  name: {binding_name}
subjects:
  - kind: ServiceAccount
    name: {self.service_name}
    namespace: {self.namespace}
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: ClusterRole
  name: cluster-admin
"""
        self.exec.fs_create_dir(conn, self.target_path)
        self.exec.fs_write_file(conn, manifest_path, manifest)
        self.exec.k8s_apply_manifest(
            conn,
            manifest_path,
            kubeconfig=self.kubeconfig,
        )
        logger.info(
            "Bound service account %s/%s to cluster-admin",
            self.namespace,
            self.service_name,
        )

    def _detect_service_port(self, conn) -> int:
        """Detect the Service port to avoid hard-coding; fall back to 8080."""
        default_port = 8080
        jsonpath = r"{.spec.ports[0].port}"
        cmd = (
            f"kubectl -n {self.namespace} get svc {self.service_name} "
            f"-o jsonpath='{jsonpath}'"
        )
        try:
            result = self.exec.execute(
                conn,
                cmd,
                group=TaskGroup.KUBERNETES,
                sudo=True,
            )
            if result:
                return int(result.strip())
        except Exception as exc:
            logger.warning(
                "Could not detect Headlamp service port, falling back to %s: %s",
                default_port,
                exc,
            )
        return default_port

    def _normalize_path_prefix(self, path_prefix: str | None) -> str:
        """Ensure the path prefix starts with a single leading slash."""
        path = path_prefix or "/"
        if not path.startswith("/"):
            path = f"/{path}"
        if len(path) > 1 and path.endswith("/"):
            path = path[:-1]
        return path

    def spin_up(self, conn) -> bool:
        logger.info("🔄 no spinning up...")
        return True

    def spin_down(self, conn) -> bool:
        logger.info("🔄 no spinning down...")
        return True

    def teardown(self, conn):
        """
        Tear down the Kubernetes Dashboard and all related RBAC/namespace.
        """
        logger.info("🗑️ Uninstalling Headlamp")
        # self.exec.k8s_delete_resource(
        #     conn,
        #     "deployment",
        #     self.service_name,
        #     namespace=self.namespace,
        # )
        # self.exec.k8s_delete_resource(
        #     conn,
        #     "service",
        #     self.service_name,
        #     namespace=self.namespace,
        # )
        # self.exec.k8s_delete_resource(
        #     conn,
        #     "svc",
        #     self.service_name,
        #     namespace=self.namespace,
        # )
        self.exec.helm_uninstall(
            conn,
            release=self.service_name,
            namespace=self.namespace,
            kubeconfig=self.kubeconfig,
        )
        logger.info("✅ Headlamp uninstall complete")
        self.state = "un-initialized"

    def check(self, conn) -> Dict:
        return dict()

    def get_secrets(self) -> Dict[str, Dict]:
        return {}
