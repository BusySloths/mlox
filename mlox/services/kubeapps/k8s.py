import time
import logging
import json  # Added for parsing JSON output
from dataclasses import dataclass, field
from typing import Dict

from mlox.service import AbstractService
from mlox.remote import exec_command, fs_create_dir, fs_delete_dir

logger = logging.getLogger(__name__)


@dataclass
class KubeAppsService(AbstractService):
    namespace: str = "kubeapps"
    kubeconfig: str = "/etc/rancher/k3s/k3s.yaml"
    release_name: str = "kubeapps"
    chart_repo: str = "bitnami"
    chart_name: str = "bitnami/kubeapps"
    chart_repo_url: str = "https://charts.bitnami.com/bitnami"
    node_port: int = 30080

    def setup(self, conn) -> None:
        logger.info("🔧 Installing KubeApps")

        # ensure target path exists
        fs_create_dir(conn, self.target_path)

        name = self.namespace
        attempts = 0
        exists = True
        while exists:
            name_exists = exec_command(
                conn,
                f"kubectl get namespace {self.namespace} --kubeconfig {self.kubeconfig}",
                sudo=True,
            )
            exists = False
            if name_exists:
                logger.info(
                    f"Namespace {self.namespace} already exists, skipping creation."
                )
                self.namespace = name + f"-{attempts}"
                attempts += 1
                exists = True

        # add & update Helm repo
        exec_command(
            conn, f"helm repo add {self.chart_repo} {self.chart_repo_url}", sudo=True
        )
        exec_command(conn, "helm repo update", sudo=True)

        # exec_command(
        #     conn,
        #     # f"helm install kubeapps bitnami/kubeapps -n kubeapps"
        #     f"helm upgrade --install {self.release_name} {self.chart_name} "
        #     f"--kubeconfig {self.kubeconfig} "
        #     f"--namespace {self.namespace} --create-namespace "
        #     f"--set frontend.service.type=LoadBalancer ",
        #     sudo=True,
        # )
        # TODO: can produce an error if the release already existed and is in the process of being terminated.

        # # install or upgrade KubeApps with NodePort
        res = exec_command(
            conn,
            f"helm upgrade --install {self.release_name} {self.chart_name} "
            f"--kubeconfig {self.kubeconfig} "
            f"--namespace {self.namespace} --create-namespace "
            f"--set frontend.service.type=NodePort "
            f"--set frontend.service.nodePort={self.node_port}",
            sudo=True,
        )
        if not res:
            logger.error("Failed to install or upgrade KubeApps.")
            self.state = "unknown"
            return

        # expose via NodePort and record URL
        # node_ip, service_port = self.expose_kubeapps_nodeport(conn)
        node_ip = conn.host
        service_port = self.node_port
        self.service_ports["KubeApps"] = service_port
        self.service_urls["KubeApps"] = f"http://{node_ip}:{service_port}"
        self.state = "running"

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

        patch = (
            f"kubectl -n {namespace} patch svc {svc_name} "
            f'-p \'{{"spec":{{"type":"NodePort","ports":[{{'
            f'"port":{port},"targetPort":{port},"nodePort":{node_port}'
            f"}}]}}}}'"
        )
        exec_command(conn, patch, sudo=True)

        node_ip = conn.host
        logger.info(f"KubeApps exposed at http://{node_ip}:{node_port}")
        return node_ip, node_port

    def teardown(self, conn) -> None:
        logger.info("🗑️ Uninstalling KubeApps")

        # uninstall Helm release
        exec_command(
            conn,
            f"helm uninstall {self.release_name} --namespace {self.namespace} --no-hooks --kubeconfig {self.kubeconfig} || true",
            sudo=True,
        )
        # remove namespace
        exec_command(
            conn,
            f"kubectl delete namespace {self.namespace} --ignore-not-found --now=true --wait=false",
            sudo=True,
        )
        # clean up files
        fs_delete_dir(conn, self.target_path)
        logger.info("✅ KubeApps uninstall complete")
        self.state = "un-initialized"

    def spin_up(self, conn) -> bool:
        logger.info("🔄 no spinning up…")
        return True

    def spin_down(self, conn) -> bool:
        logger.info("🔄 no spinning down…")
        return True

    def check(self, conn) -> Dict:
        helm_status_cmd = f"helm status {self.release_name} --kubeconfig {self.kubeconfig} --namespace {self.namespace} -o json"
        helm_result = exec_command(conn, helm_status_cmd, sudo=True)

        # if helm_result.ok:
        #     try:
        #         status_json = json.loads(helm_result.stdout.strip())
        #         release_state = (
        #             status_json.get("info", {}).get("status", "unknown").lower()
        #         )

        #         if release_state == "deployed":
        #             return {"status": "running", "details": "Helm release is deployed."}
        #         elif release_state in ["uninstalling", "pending-delete"]:
        #             return {
        #                 "status": "terminating",
        #                 "details": f"Helm release status: {release_state}.",
        #             }
        #         elif release_state == "uninstalled":
        #             release_definitely_gone_from_helm = True
        #         else:  # e.g., failed, pending-install, pending-upgrade
        #             return {
        #                 "status": "error",
        #                 "details": f"Helm release status: {release_state}.",
        #             }
        #     except json.JSONDecodeError:
        #         helm_error = "Failed to parse helm status JSON."
        #         # Proceed to namespace check as Helm status is unreliable
        # else:
        #     if "release: not found" in helm_result.stderr.lower():
        #         release_definitely_gone_from_helm = True
        #     else:
        #         helm_error = (
        #             helm_result.stderr.strip()
        #             if helm_result.stderr
        #             else f"Helm command failed with code {helm_result.return_code}"
        #         )
        #         # If Helm command failed for other reasons, it's an error, but we can still check namespace as a fallback.

        # # 2. If Helm release is gone or status was inconclusive, check namespace
        # if release_definitely_gone_from_helm or (not helm_result.ok and not helm_error):
        #     ns_status_cmd = f"kubectl get namespace {self.namespace} -o jsonpath='{{.status.phase}}'"
        #     ns_result = conn.sudo(ns_status_cmd, warn=True, hide=True)

        #     if ns_result.ok:
        #         namespace_phase = ns_result.stdout.strip()
        #         if namespace_phase == "Terminating":
        #             return {
        #                 "status": "terminating",
        #                 "details": "Namespace is terminating.",
        #             }
        #         elif namespace_phase == "Active":
        #             if release_definitely_gone_from_helm:
        #                 return {
        #                     "status": "torn_down",
        #                     "details": "Helm release uninstalled, namespace is active.",
        #                 }
        #             else:  # Helm status was inconclusive, but namespace is active
        #                 return {
        #                     "status": "unknown",
        #                     "details": f"Namespace is Active. Helm status inconclusive: {helm_error or 'Not found'}",
        #                 }
        #     else:
        #         if "notfound" in (ns_result.stderr or "").lower().replace(
        #             " ", ""
        #         ):  # Check for "namespaces ... not found"
        #             return {
        #                 "status": "torn_down",
        #                 "details": "Helm release and namespace not found.",
        #             }
        #         else:
        #             ns_error_details = (
        #                 ns_result.stderr.strip()
        #                 if ns_result.stderr
        #                 else f"kubectl command failed with code {ns_result.return_code}"
        #             )
        #             return {
        #                 "status": "error",
        #                 "details": f"Failed to get namespace status: {ns_error_details}. Helm status: {helm_error or 'Release not found or uninstalled'}",
        #             }

        # # If helm status failed for a reason other than "not found" and we couldn't determine from namespace
        # if helm_error:
        #     self.state = "unknown"
        #     return {
        #         "status": "error",
        #         "details": f"Helm error: {helm_error}. Namespace status not definitively checked or also problematic.",
        #     }

        # return {"status": "unknown", "details": "Could not determine KubeApps status."}
        return {"status": helm_result}

    def get_secrets(self) -> Dict[str, Dict]:
        return {}
