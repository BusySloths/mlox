import time
import logging
from dataclasses import dataclass, field
from typing import Dict

from mlox.service import AbstractService
from mlox.remote import exec_command, fs_create_dir, fs_delete_dir

logger = logging.getLogger(__name__)


@dataclass
class K8sDashboardService(AbstractService):
    namespace: str = "kubeapps"
    release_name: str = "kubeapps"

    def setup(self, conn) -> None:
        logger.info("🔧 Installing KubeApps (LoadBalancer only)")

        fs_create_dir(conn, self.target_path)
        exec_command(
            conn, "helm repo add bitnami https://charts.bitnami.com/bitnami", sudo=True
        )
        exec_command(conn, "helm repo update", sudo=True)

        # helm_install_cmd = (
        #     f"KUBECONFIG=/etc/rancher/k3s/k3s.yaml "
        #     f"helm upgrade --install {self.release_name} bitnami/kubeapps "
        #     # f"--version {KUBEAPPS_CHART_VERSION} "
        #     f"--namespace {self.namespace} "
        #     f"--create-namespace "
        #     f"--set frontend.service.type=LoadBalancer "
        #     f"--set frontend.service.port={self.http_port} "
        #     f"--set postgresql.enabled=true "
        #     f"--set kubeappsapis.serviceAccount.create=true "
        #     f"--set rbac.create=true "
        #     f"--set ingress.enabled=true "
        #     f"--set ingress.hostname=kubeapps.local "
        #     f"--set ingress.tls=true "
        #     f"--set ingress.selfSigned=true "
        #     f"--set postgresql.enabled=true "
        #     f"--set kubeappsapis.serviceAccount.create=true "
        #     f"--set rbac.create=true "
        #     f"--wait --timeout 10m"
        # )
        # exec_command(conn, helm_install_cmd, sudo=True)

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

    def spin_up(self, conn) -> bool:
        logger.info("🔄 no spinning up...")
        return True

    def spin_down(self, conn) -> bool:
        logger.info("🔄 no spinning down...")
        return True

    def teardown(self, conn):
        logger.info(f"🗑 Uninstalling K8S Dashboard")
        exec_command(
            conn,
            f"helm uninstall {self.release_name} -n {self.namespace} --wait --timeout 5m",
            sudo=True,
        )
        fs_delete_dir(conn, self.target_path)

    def check(self, conn) -> Dict:
        return dict()
