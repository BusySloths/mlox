import pytest

from mlox.executors import TaskGroup


pytestmark = [pytest.mark.integration, pytest.mark.kubernetes]


def test_k3s_server_reports_ready_node(ubuntu_k3s_server):
    with ubuntu_k3s_server.get_server_connection() as conn:
        nodes = ubuntu_k3s_server.exec.execute(
            conn,
            "kubectl --kubeconfig /etc/rancher/k3s/k3s.yaml get nodes --no-headers",
            group=TaskGroup.KUBERNETES,
            sudo=True,
            pty=False,
        )

    assert nodes
    assert " Ready " in f" {nodes} "
