"""iptables firewall helpers for Ubuntu executors."""

from __future__ import annotations

import ipaddress
import shlex

from fabric import Connection  # type: ignore

from mlox.execution.base import TaskGroup, TaskRunnerABC
from mlox.execution.firewall_policy import FirewallIngressExtension, render_apply_script, render_persist_script
from mlox.firewall import FirewallPolicy


class FirewallMixin(TaskRunnerABC):
    def firewall_persist_policy(self, connection: Connection, policy: FirewallPolicy, ssh_port: int, *, docker: bool, ingress: FirewallIngressExtension | None = None) -> None:
        script = render_persist_script(policy, ssh_port, docker=docker, ingress=ingress)
        result = self._run_task(connection, group=TaskGroup.NETWORKING,
                                command=self._root_shell_command(script), sudo=True)
        if result is None or "MLOX_POLICY_PERSISTED" not in result.splitlines():
            raise RuntimeError("Could not persist firewall policy. Ensure the applied rules match the draft and systemd is available; persistence may be partially configured.")

    def firewall_apply_policy(self, connection: Connection, policy: FirewallPolicy, ssh_port: int, *, docker: bool, ingress: FirewallIngressExtension | None = None) -> None:
        script = render_apply_script(policy, ssh_port, docker=docker, ingress=ingress)
        result = self._run_task(connection, group=TaskGroup.NETWORKING,
                                command=self._root_shell_command(script), sudo=True)
        if result is None or "MLOX_POLICY_APPLIED" not in result.splitlines():
            detail = " Docker requires IPv4 and IPv6 DOCKER-USER chains." if docker else ""
            raise RuntimeError("Firewall policy application failed; rules may be partially changed." + detail)

    @staticmethod
    def _root_shell_command(command: str) -> str:
        return f"sh -c {shlex.quote(command)}"

    @staticmethod
    def _normalize_firewall_source(source: str) -> str:
        source = str(source).strip()
        try:
            network = ipaddress.ip_network(source, strict=False)
        except ValueError:
            return source
        if network.prefixlen == network.max_prefixlen:
            return str(network.network_address)
        return str(network)

    @classmethod
    def _iptables_teardown_commands(cls) -> list[str]:
        commands = [
            f"iptables -D INPUT -p tcp -j {cls.firewall_input_chain} 2>/dev/null || true",
            (
                f"iptables -D DOCKER-USER -p tcp -j {cls.firewall_docker_chain} "
                "2>/dev/null || true"
            ),
            f"iptables -F {cls.firewall_input_chain} 2>/dev/null || true",
            f"iptables -F {cls.firewall_docker_chain} 2>/dev/null || true",
            f"iptables -X {cls.firewall_input_chain} 2>/dev/null || true",
            f"iptables -X {cls.firewall_docker_chain} 2>/dev/null || true",
        ]
        return [cls._root_shell_command(command) for command in commands]

    @classmethod
    def _iptables_status_command(cls) -> str:
        command = (
            f"if iptables -C INPUT -p tcp -j {cls.firewall_input_chain} "
            f">/dev/null 2>&1 || iptables -C DOCKER-USER -p tcp "
            f"-j {cls.firewall_docker_chain} >/dev/null 2>&1 || "
            "iptables -C INPUT -j MLOX-POLICY-IN >/dev/null 2>&1 || "
            "ip6tables -C INPUT -j MLOX-POLICY-IN >/dev/null 2>&1; then "
            "echo Status: active; "
            "if iptables -C INPUT -j MLOX-POLICY-IN >/dev/null 2>&1 || "
            "ip6tables -C INPUT -j MLOX-POLICY-IN >/dev/null 2>&1; then "
            "if ! iptables -C INPUT -j MLOX-POLICY-IN >/dev/null 2>&1 || "
            "! ip6tables -C INPUT -j MLOX-POLICY-IN >/dev/null 2>&1; then "
            "echo 'Warning: policy missing in one address family'; fi; fi; "
            f"iptables -S {cls.firewall_input_chain} 2>/dev/null || true; "
            f"iptables -S {cls.firewall_docker_chain} 2>/dev/null || true; "
            "iptables -S MLOX-POLICY-IN 2>/dev/null || true; "
            "ip6tables -S MLOX-POLICY-IN 2>/dev/null || true; "
            "else echo Status: inactive; fi; "
            "p=$(systemctl is-enabled mlox-firewall-policy.service 2>/dev/null || true); "
            "case \"$p\" in enabled) echo Persistence: enabled;; "
            "disabled|enabled-runtime|masked|not-found) echo Persistence: disabled;; *) echo Persistence: unknown;; esac"
        )
        return cls._root_shell_command(command)

    def firewall_down(self, connection: Connection) -> str | None:
        command = "\n".join([
            "set -e",
            "if systemctl is-enabled --quiet mlox-firewall-policy.service 2>/dev/null; then systemctl disable mlox-firewall-policy.service; fi",
            "for tool in iptables ip6tables; do",
            "  while $tool -t mangle -C PREROUTING -j MLOX-INGRESS 2>/dev/null; do $tool -t mangle -D PREROUTING -j MLOX-INGRESS; done",
            "  if $tool -t mangle -S MLOX-INGRESS >/dev/null 2>&1; then $tool -t mangle -F MLOX-INGRESS; $tool -t mangle -X MLOX-INGRESS; fi",
            "  while $tool -C INPUT -j MLOX-POLICY-IN 2>/dev/null; do $tool -D INPUT -j MLOX-POLICY-IN; done",
            "  while $tool -C DOCKER-USER -j MLOX-POLICY-DOCKER 2>/dev/null; do $tool -D DOCKER-USER -j MLOX-POLICY-DOCKER; done",
            "  if $tool -S MLOX-POLICY-IN >/dev/null 2>&1; then $tool -F MLOX-POLICY-IN; $tool -X MLOX-POLICY-IN; fi",
            "  if $tool -S MLOX-POLICY-DOCKER >/dev/null 2>&1; then $tool -F MLOX-POLICY-DOCKER; $tool -X MLOX-POLICY-DOCKER; fi",
            "done",
            "echo MLOX_POLICY_DISABLED",
        ])
        result = self._run_task(connection, group=TaskGroup.NETWORKING, command=self._root_shell_command(command), sudo=True)
        if result is None:
            raise RuntimeError("Could not remove policy firewall rules; rules may be partially changed.")
        result = None
        for command in self._iptables_teardown_commands():
            result = self._run_task(
                connection,
                group=TaskGroup.NETWORKING,
                command=command,
                sudo=True,
            )
        return result

    def firewall_status(self, connection: Connection) -> str | None:
        return self._run_task(
            connection,
            group=TaskGroup.NETWORKING,
            command=self._iptables_status_command(),
            sudo=True,
        )

    @classmethod
    def _parse_iptables_allowed_rules(
        cls,
        status: str | None,
    ) -> set[tuple[int, str | None]] | None:
        if status is None:
            return None
        if "Status: inactive" in status:
            return set()

        rules: set[tuple[int, str | None]] = set()
        for line in status.splitlines():
            tokens = line.split()
            if (
                not tokens
                or tokens[:2]
                not in (
                    ["-A", cls.firewall_input_chain],
                    ["-A", cls.firewall_docker_chain],
                    ["-A", "MLOX-POLICY-IN"],
                )
                or "-j" not in tokens
            ):
                continue
            jump = tokens[tokens.index("-j") + 1]
            if jump != "ACCEPT":
                continue

            port = None
            if "--dport" in tokens:
                port_token = tokens[tokens.index("--dport") + 1]
                if port_token.isdigit():
                    port = int(port_token)
            elif "--ctorigdstport" in tokens:
                port_token = tokens[tokens.index("--ctorigdstport") + 1]
                if port_token.isdigit():
                    port = int(port_token)
            if port is None:
                continue

            source_ip = None
            if "-s" in tokens:
                source_ip = cls._normalize_firewall_source(
                    tokens[tokens.index("-s") + 1]
                )
            rules.add((port, source_ip))
        return rules

    @classmethod
    def _parse_iptables_allowed_ports(cls, status: str | None) -> set[int] | None:
        rules = cls._parse_iptables_allowed_rules(status)
        if rules is None:
            return None
        return {port for port, _ in rules}
