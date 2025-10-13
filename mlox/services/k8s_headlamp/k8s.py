import logging
from dataclasses import dataclass
from typing import Dict

from mlox.service import AbstractService

logger = logging.getLogger(__name__)


@dataclass
class K8sHeadlampService(AbstractService):
    namespace: str = "kube-system"
    service_name: str = "my-headlamp"

    def get_login_token(self, bundle) -> str:
        token = ""
        with bundle.server.get_server_connection() as conn:
            token = self.exec.k8s_create_token(
                conn,
                service_account=self.service_name,
                namespace=self.namespace,
            )
        return token

    def setup(self, conn) -> None:
        logger.info("🔧 Installing K8s Headlamp")

        kubeconfig: str = "/etc/rancher/k3s/k3s.yaml"
        src_url = f"https://kubernetes-sigs.github.io/headlamp/"

        # Add kubernetes-dashboard repository
        self.exec.helm_repo_add(
            conn,
            "headlamp",
            src_url,
            kubeconfig=kubeconfig,
        )
        # Deploy a Helm Release named "kubernetes-dashboard" using the kubernetes-dashboard chart
        self.exec.helm_upgrade_install(
            conn,
            release=self.service_name,
            chart="headlamp/headlamp",
            namespace=self.namespace,
            kubeconfig=kubeconfig,
            create_namespace=True,
        )
        node_ip, service_port = self.expose_dashboard_nodeport(conn)
        self.service_urls["Headlamp"] = f"http://{node_ip}:{service_port}"
        self.state = "running"

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
        self.exec.k8s_delete_resource(
            conn,
            "deployment",
            self.service_name,
            namespace=self.namespace,
        )
        self.exec.k8s_delete_resource(
            conn,
            "service",
            self.service_name,
            namespace=self.namespace,
        )
        self.exec.k8s_delete_resource(
            conn,
            "svc",
            self.service_name,
            namespace=self.namespace,
        )

        logger.info("✅ Headlamp uninstall complete")
        self.state = "un-initialized"

    def check(self, conn) -> Dict:
        return dict()

    def get_secrets(self) -> Dict[str, Dict]:
        return {}
