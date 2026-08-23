from __future__ import annotations

from mlox.execution.kubernetes import KubernetesMixin


class _Connection:
    def __init__(self) -> None:
        self.uploads: dict[str, bytes] = {}

    def put(self, content, remote: str) -> None:
        self.uploads[remote] = content.read()


class _Runner(KubernetesMixin):
    def __init__(self) -> None:
        self.commands: list[str] = []
        self.options: list[dict] = []

    def _run_task(self, connection, *, command, **kwargs):
        self.commands.append(command)
        self.options.append(kwargs)
        return "configured"


def test_apply_tls_secret_keeps_pem_out_of_command_history() -> None:
    connection = _Connection()
    runner = _Runner()
    certificate = "-----BEGIN CERTIFICATE-----\npublic\n-----END CERTIFICATE-----"
    private_key = "-----BEGIN PRIVATE KEY-----\nprivate\n-----END PRIVATE KEY-----"

    result = runner.k8s_apply_tls_secret(
        connection,
        "gateway-tls",
        namespace="gateway",
        certificate=certificate,
        private_key=private_key,
        kubeconfig="/etc/rancher/k3s/k3s.yaml",
    )

    assert result == "configured"
    assert certificate.encode() in connection.uploads.values()
    assert private_key.encode() in connection.uploads.values()
    history = "\n".join(runner.commands)
    assert certificate not in history
    assert private_key not in history
    assert "kubectl create secret tls gateway-tls" in history
    assert runner.commands[-2].startswith("sh -c ")
    assert runner.options[-2]["sudo"] is True
    assert runner.commands[-1].startswith("rm -f ")
