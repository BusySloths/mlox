import logging
import json
from dataclasses import dataclass
from typing import Dict

from mlox.executors import TaskGroup
from mlox.service import AbstractService, ServiceCapability

logger = logging.getLogger(__name__)


@dataclass
class KubeAppsService(AbstractService):
    capabilities = {ServiceCapability.DASHBOARD}
    namespace: str = "kubeapps"
    kubeconfig: str = "/etc/rancher/k3s/k3s.yaml"
    release_name: str = "kubeapps"
    chart_name: str = "oci://ghcr.io/sap/kubeapps/kubeapps"
    app_version: str = "v3.0.0"
    service_account_name: str = "kubeapps-admin"
    node_port: int = 30080
    ingress_port: int = 443
    ingress_path: str = ""

    def get_login_token(self, bundle) -> str:
        token = "no token"
        if not bundle.server:
            logger.error("No server connection available")
            return token
        with bundle.server.get_server_connection() as conn:
            _token = self.exec.k8s_create_token(
                conn,
                service_account=self.service_account_name,
                namespace=self.namespace,
                kubeconfig=self.kubeconfig,
            )
            if _token:
                token = _token
        return token

    def setup(self, conn) -> None:
        logger.info("🔧 Installing KubeApps")

        # ensure target path exists
        self.exec.fs_create_dir(conn, self.target_path)

        if not self._select_available_namespace(conn):
            self.state = "unknown"
            return

        # SAP publishes the maintained Kubeapps chart as an OCI artifact. Helm
        # can install it directly, so there is no repository index to add/update.
        res = self.exec.helm_upgrade_install(
            conn,
            release=self.release_name,
            chart=self.chart_name,
            namespace=self.namespace,
            kubeconfig=self.kubeconfig,
            create_namespace=True,
            values=self._helm_values(),
        )
        if not res:
            logger.error("Failed to install or upgrade KubeApps.")
            self.state = "unknown"
            return

        self._bind_service_account_cluster_admin(conn)

        host, service_port, path = self.expose_kubeapps_ingress(conn)
        self.ingress_path = path
        self.service_ports["KubeApps"] = service_port
        self.service_urls["KubeApps"] = f"https://{host}:{service_port}{path}/"
        self.state = "running"

    def expose_kubeapps_ingress(
        self,
        conn,
        ingress_name: str | None = None,
        ingress_port: int | None = None,
        host: str | None = None,
        path: str | None = None,
        backend_service_port: int = 80,
        tls_secret_name: str | None = None,
        entrypoint: str = "websecure",
    ):
        """
        Expose KubeApps through the k3s Traefik ingress controller.
        """
        ingress_name = ingress_name or f"{self.release_name}-ingress"
        ingress_port = ingress_port or self.ingress_port
        external_host = conn.host
        path = self._normalize_ingress_path(path)
        tls_secret_name = tls_secret_name or f"{ingress_name}-tls"
        host_line = f"    - host: {host}\n      http:" if host else "    - http:"
        tls_hosts = f"\n        - {host}" if host else " []"

        ingress_manifest = f"""apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: {ingress_name}
  namespace: {self.namespace}
  annotations:
    kubernetes.io/ingress.class: traefik
    traefik.ingress.kubernetes.io/router.entrypoints: {entrypoint}
    traefik.ingress.kubernetes.io/router.tls: "true"
spec:
  ingressClassName: traefik
  rules:
{host_line}
        paths:
          - path: {path}
            pathType: Prefix
            backend:
              service:
                name: {self.release_name}
                port:
                  number: {backend_service_port}
  tls:
    - hosts:{tls_hosts}
      secretName: {tls_secret_name}
"""
        manifest_path = f"{self.target_path}/{ingress_name}.yaml"
        self.exec.fs_create_dir(conn, self.target_path)
        self.exec.fs_write_file(conn, manifest_path, ingress_manifest)
        self.exec.k8s_apply_manifest(
            conn,
            manifest_path,
            namespace=self.namespace,
            kubeconfig=self.kubeconfig,
        )

        logger.info(
            "KubeApps exposed at https://%s:%s%s via ingress",
            external_host,
            ingress_port,
            path,
        )
        return external_host, ingress_port, path

    def expose_kubeapps_nodeport(
        self,
        conn,
        namespace: str | None = None,
        svc_name: str | None = None,
        port: int | None = None,
        node_port: int | None = None,
    ):
        """
        Patches the KubeApps Service to NodePort and returns (node_ip, node_port).
        """
        namespace = namespace or self.namespace
        svc_name = svc_name or self.release_name
        port = port or 80
        node_port = node_port or self.node_port

        patch_body = {
            "spec": {
                "type": "NodePort",
                "ports": [
                    {
                        "port": port,
                        "targetPort": port,
                        "nodePort": node_port,
                    }
                ],
            }
        }
        self.exec.k8s_patch_resource(
            conn,
            "svc",
            svc_name,
            patch_body,
            namespace=namespace,
        )

        node_ip = conn.host
        logger.info(f"KubeApps exposed at http://{node_ip}:{node_port}")
        return node_ip, node_port

    def teardown(self, conn) -> None:
        logger.info("🗑️ Uninstalling KubeApps")

        # uninstall Helm release
        self.exec.helm_uninstall(
            conn,
            release=self.release_name,
            namespace=self.namespace,
            kubeconfig=self.kubeconfig,
            extra_args=["--no-hooks"],
            ignore_missing=True,
        )
        # remove namespace
        self.exec.k8s_delete_resource(
            conn,
            "clusterrolebinding",
            self._cluster_role_binding_name(),
            kubeconfig=self.kubeconfig,
        )
        self.exec.k8s_delete_resource(
            conn,
            "serviceaccount",
            self.service_account_name,
            namespace=self.namespace,
            kubeconfig=self.kubeconfig,
        )
        self.exec.k8s_delete_resource(
            conn,
            "namespace",
            self.namespace,
            kubeconfig=self.kubeconfig,
            extra_args=["--now=true", "--wait=false"],
        )
        # clean up files
        self.exec.fs_delete_dir(conn, self.target_path)
        logger.info("✅ KubeApps uninstall complete")
        self.state = "un-initialized"

    def spin_up(self, conn) -> bool:
        logger.info("🔄 no spinning up…")
        return True

    def spin_down(self, conn) -> bool:
        logger.info("🔄 no spinning down…")
        return True

    def _helm_values(self) -> Dict[str, str]:
        values = {
            "frontend.service.type": "ClusterIP",
            "dashboard.image.tag": self.app_version,
            "apprepository.image.tag": self.app_version,
            "apprepository.syncImage.tag": self.app_version,
            "kubeappsapis.image.tag": self.app_version,
            "pinnipedProxy.image.tag": self.app_version,
            "ociCatalog.image.tag": self.app_version,
            "postgresql.fullnameOverride": f"{self.release_name}-postgresql",
            "postgresql.resourcesPreset": "small",
            "apprepository.watchAllNamespaces": "false",
            "apprepository.crontab": "0 */6 * * *",
        }
        values.update(self._initial_app_repositories())
        return values

    def _initial_app_repositories(self) -> Dict[str, str]:
        repositories = [
            ("jetstack", "https://charts.jetstack.io"),
            ("external-secrets", "https://charts.external-secrets.io"),
            ("cloudnative-pg", "https://cloudnative-pg.github.io/charts"),
        ]
        values = {}
        for index, (name, url) in enumerate(repositories):
            values[f"apprepository.initialRepos[{index}].name"] = name
            values[f"apprepository.initialRepos[{index}].url"] = url
        return values

    def _normalize_ingress_path(self, path: str | None = None) -> str:
        ingress_path = path or f"/{self.release_name}"
        if not ingress_path.startswith("/"):
            ingress_path = f"/{ingress_path}"
        return ingress_path.rstrip("/") or "/"

    def _select_available_namespace(self, conn, max_attempts: int = 20) -> bool:
        base_namespace = self.namespace
        base_release_name = self.release_name

        for attempt in range(max_attempts):
            candidate = f"{base_namespace}-{attempt}"
            phase = self._namespace_phase(conn, candidate)
            if not phase:
                self.namespace = candidate
                self.release_name = f"{base_release_name}-{attempt}"
                logger.info(
                    "Installing KubeApps into namespace %s.",
                    self.namespace,
                )
                return True
            logger.info(
                "Namespace %s is unavailable with phase %s.",
                candidate,
                phase,
            )

        logger.error(
            "No available KubeApps namespace found after %s attempts starting at %s.",
            max_attempts,
            base_namespace,
        )
        return False

    def _namespace_phase(self, conn, namespace: str | None = None) -> str:
        namespace = namespace or self.namespace
        jsonpath = r"{.status.phase}"
        cmd = (
            f"kubectl --kubeconfig {self.kubeconfig} get namespace {namespace} "
            f"--ignore-not-found -o jsonpath=\"{jsonpath}\""
        )
        try:
            result = self.exec.execute(
                conn,
                cmd,
                group=TaskGroup.KUBERNETES,
                sudo=True,
            )
            return result.strip() if result else ""
        except Exception as exc:
            logger.warning("Could not read namespace %s phase: %s", namespace, exc)
            return ""

    def _cluster_role_binding_name(self) -> str:
        return f"{self.namespace}-{self.service_account_name}-cluster-admin"

    def _bind_service_account_cluster_admin(self, conn) -> None:
        binding_name = self._cluster_role_binding_name()
        manifest_path = f"{self.target_path}/{binding_name}.yaml"
        manifest = f"""apiVersion: v1
kind: ServiceAccount
metadata:
  name: {self.service_account_name}
  namespace: {self.namespace}
---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRoleBinding
metadata:
  name: {binding_name}
subjects:
  - kind: ServiceAccount
    name: {self.service_account_name}
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
            self.service_account_name,
        )

    def _detect_frontend_node_port(self, conn) -> int:
        service_name = self.release_name
        jsonpaths = [
            r"{.spec.ports[?(@.name=='http')].nodePort}",
            r"{.spec.ports[0].nodePort}",
        ]
        for jsonpath in jsonpaths:
            cmd = (
                f"kubectl --kubeconfig {self.kubeconfig} -n {self.namespace} "
                f"get svc {service_name} -o jsonpath=\"{jsonpath}\""
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
                    "Could not detect KubeApps NodePort with jsonpath %s: %s",
                    jsonpath,
                    exc,
                )
        return self.node_port

    def check(self, conn) -> Dict:
        helm_result = self.exec.helm_status(
            conn,
            release=self.release_name,
            namespace=self.namespace,
            kubeconfig=self.kubeconfig,
            output_format="json",
        )
        if not helm_result:
            return {"status": "unknown", "details": "Helm status returned no output."}

        try:
            status_json = json.loads(helm_result)
        except json.JSONDecodeError:
            return {
                "status": "unknown",
                "details": "Failed to parse Helm status JSON.",
                "helm_status": helm_result,
            }

        release_state = status_json.get("info", {}).get("status", "unknown").lower()
        if release_state == "deployed":
            return {"status": "running", "details": "Helm release is deployed."}
        if release_state in {"uninstalling", "pending-delete"}:
            return {
                "status": "terminating",
                "details": f"Helm release status: {release_state}.",
            }
        if release_state in {"uninstalled", "superseded"}:
            return {
                "status": "stopped",
                "details": f"Helm release status: {release_state}.",
            }
        if release_state in {"failed", "pending-install", "pending-upgrade"}:
            return {
                "status": "error",
                "details": f"Helm release status: {release_state}.",
            }
        return {
            "status": "unknown",
            "details": f"Helm release status: {release_state}.",
        }

    def get_secrets(self) -> Dict[str, Dict]:
        return {}
