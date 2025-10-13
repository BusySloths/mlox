import logging
from dataclasses import dataclass
from typing import Dict

from mlox.executors import TaskGroup
from mlox.service import AbstractService

logger = logging.getLogger(__name__)


@dataclass
class K8sDashboardService(AbstractService):
    namespace: str = "kubernetes-dashboard"
    release_name: str = "dashboard"

    def get_login_token(self, bundle) -> str:
        token = ""
        with bundle.server.get_server_connection() as conn:
            token = self.exec.execute(
                conn,
                "kubectl -n kubernetes-dashboard create token admin-user",
                group=TaskGroup.KUBERNETES,
                sudo=True,
            )
        return token

    def setup(self, conn) -> None:
        logger.info("🔧 Installing K8s Dashboard")
        self.exec.fs_create_dir(conn, self.target_path)
        self.exec.fs_copy(conn, self.template, f"{self.target_path}/service_account.yaml")
        # self.exec.tls_setup(conn, conn.host, self.target_path)

        kubeconfig: str = "/etc/rancher/k3s/k3s.yaml"

        # self.exec.exec_command(
        #     conn,
        #     "kubectl apply -f https://raw.githubusercontent.com/kubernetes/dashboard/v2.7.0/aio/deploy/recommended.yaml",
        #     sudo=True,
        # )

        version = "7.13.0"
        src_url_newest = f"https://kubernetes.github.io/dashboard/"
        src_url = f"https://github.com/kubernetes/dashboard/tree/release/{version}/"

        # Add kubernetes-dashboard repository
        self.exec.execute(
            conn,
            f"helm repo add kubernetes-dashboard {src_url} --kubeconfig {kubeconfig}",
            group=TaskGroup.KUBERNETES,
            sudo=True,
        )
        # self.exec.exec_command(
        #     conn,
        #     f"helm repo add kubernetes-dashboard https://kubernetes.github.io/dashboard/ --kubeconfig {kubeconfig}",
        #     sudo=True,
        # )
        # Deploy a Helm Release named "kubernetes-dashboard" using the kubernetes-dashboard chart
        self.exec.execute(
            conn,
            f"helm upgrade --install kubernetes-dashboard kubernetes-dashboard/kubernetes-dashboard --create-namespace --namespace kubernetes-dashboard --kubeconfig {kubeconfig}",
            group=TaskGroup.KUBERNETES,
            sudo=True,
        )
        self.exec.execute(
            conn,
            f"kubectl apply -f {self.target_path}/service_account.yaml",
            group=TaskGroup.KUBERNETES,
            sudo=True,
        )
        # node_ip, service_port = self.setup_k8s_dashboard_traefik_ingress(conn)
        node_ip, service_port = self.expose_dashboard_nodeport(conn)
        # self.service_ports["Kubernetes Dashboard"] = self.exec.exec_command(
        #     conn,
        #     "kubectl -n kubernetes-dashboard get svc kubernetes-dashboard -o jsonpath='{.spec.ports[0].port}{\"\\n\"}'",
        #     sudo=True,
        # )
        self.service_ports["Kubernetes Dashboard"] = service_port
        self.service_urls["Kubernetes Dashboard"] = f"https://{node_ip}:{service_port}"
        self.state = "running"

    def expose_dashboard_nodeport(
        self,
        conn,
        namespace="kubernetes-dashboard",
        svc_name="kubernetes-dashboard-kong-proxy",
        node_port=32000,
        api_node_port: int = 30081,
    ):
        """
        Converts the Dashboard Service to NodePort and returns (node_ip, node_port).
        """
        # 1) Patch the Service to add a name to the port, which is required.
        patch = (
            f"kubectl -n {namespace} patch svc {svc_name} "
            f'-p \'{{"spec":{{"type":"NodePort","ports":[{{'
            f'"name":"https","port":443,"targetPort":8443,"nodePort":{node_port}'
            f"}}]}}}}'"
        )

        self.exec.execute(
            conn,
            patch,
            group=TaskGroup.KUBERNETES,
            sudo=True,
        )
        node_ip = conn.host

        logger.info(f"Dashboard exposed at https://{node_ip}:{node_port}")
        return node_ip, node_port

    #     def setup_k8s_dashboard_traefik_ingress(
    #         self,
    #         conn,
    #         namespace="kubernetes-dashboard",
    #         traefik_ns="kube-system",
    #         secret_name="dashboard-tls",
    #         node_port=32443,
    #     ):
    #         """
    #         Expose the Kubernetes Dashboard externally over HTTPS via Traefik:
    #         - Creates a TLS secret from cert.pem/key.pem in self.target_path
    #         - Patches Traefik svc → NodePort (port 443 → nodePort)
    #         - Applies an Ingress for https://<node-ip>:node_port
    #         Returns (node_ip, node_port).
    #         """
    #         logger.info("🔧 Configuring Traefik Ingress for K8s Dashboard")

    #         # Paths to your cert/key (next to service_account.yaml)
    #         cert_path = f"{self.target_path}/cert.pem"
    #         key_path = f"{self.target_path}/key.pem"

    #         cmds = [
    #             # 1) create/update the TLS Secret
    #             (
    #                 f"kubectl -n {namespace} create secret tls {secret_name} "
    #                 f"--cert={cert_path} --key={key_path} "
    #                 "--dry-run=client -o yaml | kubectl apply -f -"
    #             ),
    #             # 2) patch Traefik Service to NodePort on 443 → node_port
    #             (
    #                 f"kubectl -n {traefik_ns} patch svc traefik "
    #                 f'-p \'{{"spec":{{"type":"NodePort","ports":[{{'
    #                 f'"name":"https-traefik","port":443,"targetPort":443,"nodePort":{node_port}}}]}}}}\''
    #             ),
    #         ]

    #         # run secret + patch
    #         for cmd in cmds:
    #             logger.debug(f"Running: {cmd}")
    #             self.exec.exec_command(conn, cmd, sudo=True)

    #         # 3) discover the node's IP
    #         # ip_cmd = "hostname -I | awk '{print $1}'"
    #         node_ip = conn.host

    #         # 4) apply the Ingress manifest
    #         ingress_yaml = f"""apiVersion: networking.k8s.io/v1
    # kind: Ingress
    # metadata:
    # name: kubernetes-dashboard
    # namespace: {namespace}
    # annotations:
    #     kubernetes.io/ingress.class: traefik
    # spec:
    # tls:
    # - hosts:
    #     - "{node_ip}"
    #     secretName: {secret_name}
    # rules:
    # - host: "{node_ip}"
    #     http:
    #     paths:
    #     - path: /
    #         pathType: Prefix
    #         backend:
    #         service:
    #             name: kubernetes-dashboard
    #             port:
    #             number: 443
    #         """
    #         ingress_cmd = f"""cat <<EOF | kubectl apply -f -{ingress_yaml} EOF"""
    #         logger.debug("Applying Dashboard Ingress")
    #         self.exec.exec_command(conn, ingress_cmd, sudo=True)

    #         logger.info(f"✅ Traefik Ingress ready at https://{node_ip}:{node_port}")
    #         return node_ip, node_port

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
        logger.info("🗑️ Uninstalling K8s Dashboard")

        manifest_url = "https://raw.githubusercontent.com/kubernetes/dashboard/v2.7.0/aio/deploy/recommended.yaml"
        sa_file = f"{self.target_path}/service_account.yaml"

        cmds = [
            # delete the core dashboard objects
            f"kubectl delete -f {manifest_url} --ignore-not-found",
            # delete your custom SA + RBAC
            f"kubectl delete -f {sa_file} --ignore-not-found",
            # delete the ClusterRoleBinding you created
            "kubectl delete clusterrolebinding admin-user --ignore-not-found",
            # delete the ServiceAccount in the kubernetes-dashboard namespace
            "kubectl delete serviceaccount admin-user -n kubernetes-dashboard --ignore-not-found",
            # finally, delete the namespace itself
            "kubectl delete namespace kubernetes-dashboard --ignore-not-found",
        ]

        for cmd in cmds:
            logger.debug(f"Running: {cmd}")
            self.exec.execute(
                conn,
                cmd,
                group=TaskGroup.KUBERNETES,
                sudo=True,
            )

        self.exec.fs_delete_dir(conn, self.target_path)
        logger.info("✅ K8s Dashboard uninstall complete")
        self.state = "un-initialized"

    def check(self, conn) -> Dict:
        return dict()

    def get_secrets(self) -> Dict[str, Dict]:
        return {}
