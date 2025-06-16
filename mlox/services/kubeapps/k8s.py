import time
import logging
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

        # add & update Helm repo
        exec_command(
            conn, f"helm repo add {self.chart_repo} {self.chart_repo_url}", sudo=True
        )
        exec_command(conn, "helm repo update", sudo=True)

        exec_command(
            conn,
            f"helm install kubeapps bitnami/kubeapps -n kubeapps \
                --set frontend.service.type=LoadBalancer",
            sudo=True,
        )

        # # install or upgrade KubeApps with NodePort
        # exec_command(
        #     conn,
        #     f"helm upgrade --install {self.release_name} {self.chart_name} "
        #     f"--kubeconfig {self.kubeconfig} "
        #     f"--namespace {self.namespace} --create-namespace "
        #     f"--set frontend.service.type=NodePort "
        #     f"--set frontend.service.nodePort={self.node_port}",
        #     sudo=True,
        # )

        # expose via NodePort and record URL
        node_ip, service_port = self.expose_kubeapps_nodeport(conn)
        self.service_ports["KubeApps"] = service_port
        self.service_url = f"http://{node_ip}:{service_port}"

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
            f"helm uninstall {self.release_name} --namespace {self.namespace} || true",
            sudo=True,
        )
        # remove namespace
        exec_command(
            conn,
            f"kubectl delete namespace {self.namespace} --ignore-not-found",
            sudo=True,
        )
        # clean up files
        fs_delete_dir(conn, self.target_path)

        logger.info("✅ KubeApps uninstall complete")

    def spin_up(self, conn) -> bool:
        logger.info("🔄 no spinning up…")
        return True

    def spin_down(self, conn) -> bool:
        logger.info("🔄 no spinning down…")
        return True

    def check(self, conn) -> Dict:
        """
        Returns the Helm status of the KubeApps release.
        """
        status = exec_command(
            conn,
            f"helm status {self.release_name} --namespace {self.namespace}",
            sudo=True,
        )
        return {"status": status}
