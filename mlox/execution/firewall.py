"""iptables firewall helpers for Ubuntu executors."""

from __future__ import annotations

import ipaddress
import shlex
from typing import Mapping, Sequence

from fabric import Connection  # type: ignore

from mlox.execution.base import TaskGroup, TaskRunnerABC


class FirewallMixin(TaskRunnerABC):
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
    def _normalize_firewall_rules(
        cls,
        ports: Sequence[int] | Mapping[int, Sequence[str] | None],
        source_ips_by_port: Mapping[int, Sequence[str] | None] | None = None,
    ) -> set[tuple[int, str | None]]:
        if isinstance(ports, Mapping) and source_ips_by_port is None:
            source_map = {int(port): sources for port, sources in ports.items()}
            port_values = source_map.keys()
        else:
            source_map = {
                int(port): sources
                for port, sources in (source_ips_by_port or {}).items()
            }
            port_values = ports

        rules: set[tuple[int, str | None]] = set()
        for port_value in port_values:
            port = int(port_value)
            if port <= 0:
                continue

            sources = source_map.get(port)
            if not sources:
                rules.add((port, None))
                continue

            for source in sources:
                source_ip = cls._normalize_firewall_source(str(source))
                if source_ip:
                    rules.add((port, source_ip))
        return rules

    @classmethod
    def _iptables_setup_commands(cls) -> list[str]:
        return [
            f"iptables -N {cls.firewall_input_chain} 2>/dev/null || true",
            f"iptables -N {cls.firewall_docker_chain} 2>/dev/null || true",
            "iptables -N DOCKER-USER 2>/dev/null || true",
            (
                f"iptables -C INPUT -p tcp -j {cls.firewall_input_chain} "
                f"2>/dev/null || iptables -I INPUT 1 -p tcp -j {cls.firewall_input_chain}"
            ),
            (
                f"iptables -C DOCKER-USER -p tcp -j {cls.firewall_docker_chain} "
                f"2>/dev/null || iptables -I DOCKER-USER 1 -p tcp "
                f"-j {cls.firewall_docker_chain}"
            ),
        ]

    @classmethod
    def _iptables_teardown_commands(cls) -> list[str]:
        return [
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

    @classmethod
    def _iptables_status_command(cls) -> str:
        return (
            f"if iptables -C INPUT -p tcp -j {cls.firewall_input_chain} "
            f">/dev/null 2>&1 || iptables -C DOCKER-USER -p tcp "
            f"-j {cls.firewall_docker_chain} >/dev/null 2>&1; then "
            "echo 'Status: active'; "
            f"iptables -S {cls.firewall_input_chain} 2>/dev/null || true; "
            f"iptables -S {cls.firewall_docker_chain} 2>/dev/null || true; "
            "else echo 'Status: inactive'; fi"
        )

    @classmethod
    def _iptables_input_allow_command(
        cls, port: int, source_ip: str | None = None
    ) -> str:
        if source_ip:
            source = shlex.quote(source_ip)
            return (
                f"iptables -A {cls.firewall_input_chain} -p tcp "
                f"-s {source} --dport {port} -j ACCEPT"
            )
        return f"iptables -A {cls.firewall_input_chain} -p tcp --dport {port} -j ACCEPT"

    @classmethod
    def _iptables_docker_allow_command(
        cls, port: int, source_ip: str | None = None
    ) -> str:
        if source_ip:
            source = shlex.quote(source_ip)
            return (
                f"iptables -A {cls.firewall_docker_chain} -p tcp "
                f"-s {source} -m conntrack --ctorigdstport {port} -j ACCEPT"
            )
        return (
            f"iptables -A {cls.firewall_docker_chain} -p tcp "
            f"-m conntrack --ctorigdstport {port} -j ACCEPT"
        )

    @classmethod
    def _iptables_rule_commands(cls, rules: set[tuple[int, str | None]]) -> list[str]:
        commands = [
            f"iptables -F {cls.firewall_input_chain}",
            f"iptables -F {cls.firewall_docker_chain}",
            f"iptables -A {cls.firewall_input_chain} -i lo -j ACCEPT",
            (
                f"iptables -A {cls.firewall_input_chain} -m conntrack "
                "--ctstate ESTABLISHED,RELATED -j ACCEPT"
            ),
            (
                f"iptables -A {cls.firewall_docker_chain} -m conntrack "
                "--ctstate ESTABLISHED,RELATED -j ACCEPT"
            ),
            f"iptables -A {cls.firewall_docker_chain} -i docker0 -j RETURN",
            f"iptables -A {cls.firewall_docker_chain} -i br+ -j RETURN",
        ]
        ports = sorted({port for port, _ in rules})
        for port in ports:
            port_rules = sorted(
                (
                    (rule_port, source)
                    for rule_port, source in rules
                    if rule_port == port
                ),
                key=lambda rule: rule[1] or "",
            )
            for _, source in port_rules:
                commands.append(cls._iptables_input_allow_command(port, source))
                commands.append(cls._iptables_docker_allow_command(port, source))

        commands.extend(
            [
                f"iptables -A {cls.firewall_input_chain} -j DROP",
                (
                    f"iptables -A {cls.firewall_docker_chain} -o docker0 "
                    "-m conntrack --ctstate NEW -j DROP"
                ),
                (
                    f"iptables -A {cls.firewall_docker_chain} -o br+ "
                    "-m conntrack --ctstate NEW -j DROP"
                ),
            ]
        )
        return commands

    def _iptables_apply_firewall_rules(
        self,
        connection: Connection,
        rules: set[tuple[int, str | None]],
    ) -> None:
        for command in self._iptables_setup_commands():
            self._run_task(
                connection,
                group=TaskGroup.NETWORKING,
                command=command,
                sudo=True,
            )
        for command in self._iptables_rule_commands(rules):
            self._run_task(
                connection,
                group=TaskGroup.NETWORKING,
                command=command,
                sudo=True,
            )

    def firewall_up(
        self,
        connection: Connection,
        ports: Sequence[int] | Mapping[int, Sequence[str] | None],
        source_ips_by_port: Mapping[int, Sequence[str] | None] | None = None,
    ) -> str | None:
        rules = self._normalize_firewall_rules(ports, source_ips_by_port)
        self._iptables_apply_firewall_rules(connection, rules)
        return self.firewall_status(connection)

    def firewall_down(self, connection: Connection) -> str | None:
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

    def firewall_update(
        self,
        connection: Connection,
        ports: Sequence[int] | Mapping[int, Sequence[str] | None],
        source_ips_by_port: Mapping[int, Sequence[str] | None] | None = None,
    ) -> str | None:
        status = self.firewall_status(connection)
        if status is None or "Status: inactive" in status:
            return status

        desired_rules = self._normalize_firewall_rules(ports, source_ips_by_port)
        self._iptables_apply_firewall_rules(connection, desired_rules)
        return self.firewall_status(connection)
