import time
import logging
from dataclasses import dataclass, field
from typing import Dict

from mlox.service import AbstractService
from mlox.remote import exec_command, fs_create_dir, fs_delete_dir

logger = logging.getLogger(__name__)
KUBEAPPS_CHART_VERSION = "18.0.1"


@dataclass
class KubeAppsService(AbstractService):
    namespace: str = "kubeapps"
    release_name: str = "kubeapps"
    http_port: int = 80
    service_url: str = field(default="", init=False)
    access_token: str = field(default="", init=False)
    service_ports: Dict[str, int] = field(default_factory=dict, init=False)

    def setup(self, conn) -> None:
        logger.info("🔧 Installing KubeApps (LoadBalancer only)")

        fs_create_dir(conn, self.target_path)
        exec_command(
            conn, "helm repo add bitnami https://charts.bitnami.com/bitnami", sudo=True
        )
        exec_command(conn, "helm repo update", sudo=True)

        helm_install_cmd = (
            f"KUBECONFIG=/etc/rancher/k3s/k3s.yaml "
            f"helm upgrade --install {self.release_name} bitnami/kubeapps "
            # f"--version {KUBEAPPS_CHART_VERSION} "
            f"--namespace {self.namespace} "
            f"--create-namespace "
            f"--set frontend.service.type=LoadBalancer "
            f"--set frontend.service.port={self.http_port} "
            f"--set postgresql.enabled=true "
            f"--set kubeappsapis.serviceAccount.create=true "
            f"--set rbac.create=true "
            f"--set ingress.enabled=true "
            f"--set ingress.hostname=kubeapps.local "
            f"--set ingress.tls=true "
            f"--set ingress.selfSigned=true "
            f"--set postgresql.enabled=true "
            f"--set kubeappsapis.serviceAccount.create=true "
            f"--set rbac.create=true "
            f"--wait --timeout 10m"
        )
        # exec_command(conn, helm_install_cmd, sudo=True)
        # exec_command(
        #     conn,
        #     f"kubectl wait ns {self.namespace} --for=condition=Active --timeout=60s",
        #     sudo=True,
        # )

        exec_command(
            conn,
            f"KUBECONFIG=/etc/rancher/k3s/k3s.yaml helm repo add bitnami-aks https://marketplace.azurecr.io/helm/v1/repo ",
            sudo=True,
        )
        exec_command(
            conn,
            f"KUBECONFIG=/etc/rancher/k3s/k3s.yaml kubectl create namespace kubeapps ",
            sudo=True,
        )
        exec_command(
            conn,
            f"KUBECONFIG=/etc/rancher/k3s/k3s.yaml helm install my-kubeapps bitnami-aks/kubeapps --version 10.3.5 ",
            sudo=True,
        )

        # Get LoadBalancer IP or hostname
        # logger.info("🌐 Waiting for LoadBalancer IP...")
        # lb_ip_or_hostname = ""
        # for i in range(30):
        #     for field in ["ip", "hostname"]:
        #         cmd = (
        #             f"kubectl get svc -n {self.namespace} {self.release_name}-kubeapps "
        #             f"-o jsonpath='{{.status.loadBalancer.ingress[0].{field}}}'"
        #         )
        #         result = exec_command(conn, cmd, sudo=True, pty=False).strip()
        #         if result and result != "<none>":
        #             lb_ip_or_hostname = result
        #             break
        #     if lb_ip_or_hostname:
        #         break
        #     logger.info(f"⌛ Waiting... attempt {i + 1}/30")
        #     time.sleep(10)

        # if lb_ip_or_hostname:
        #     self.service_url = f"http://{lb_ip_or_hostname}"
        #     self.service_ports["KubeApps UI (LoadBalancer)"] = self.http_port
        #     logger.info(f"✅ KubeApps available at: {self.service_url}")
        # else:
        #     logger.warning("⚠️ Could not determine LoadBalancer IP.")

        # Get access token
        sa = "kubeapps-internal-kubeappsapis"
        token_cmd = f"kubectl create token {sa} -n {self.namespace} --duration 8760h"
        try:
            token = exec_command(conn, token_cmd, sudo=True, pty=False).strip()
            self.access_token = token
            logger.info("🔑 KubeApps access token retrieved successfully.")
        except Exception as e:
            logger.warning(f"Failed to retrieve token: {e}")

    def spin_up(self, conn) -> bool:
        logger.info("🔄 no spinning up...")
        return True

    def spin_down(self, conn) -> bool:
        logger.info("🔄 no spinning down...")
        return True

    def teardown(self, conn):
        logger.info(f"🗑 Uninstalling KubeApps '{self.release_name}'")
        exec_command(
            conn,
            f"helm uninstall {self.release_name} -n {self.namespace} --wait --timeout 5m",
            sudo=True,
        )
        fs_delete_dir(conn, self.target_path)

    def check(self, conn) -> Dict:
        status = {
            "release": self.release_name,
            "namespace": self.namespace,
            "url": self.service_url,
            "ports": self.service_ports,
            "access_token": self.access_token,
        }
        return status
