import streamlit as st

from typing import Any, Dict, List, Sequence

from mlox.config import ServiceConfig
from mlox.executors import UbuntuTaskExecutor
from mlox.infra import Infrastructure, Bundle
from mlox.servers.ubuntu.native import UbuntuNativeServer


def _is_firewall_up(firewall_status: str | None) -> bool:
    return bool(firewall_status and "Status: active" in firewall_status)


def _collect_firewall_port_rows(
    bundle: Bundle, server: UbuntuNativeServer
) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = [
        {
            "port_number": int(server.port),
            "service": "Server",
            "port_name": "SSH",
        }
    ]
    seen = {(int(server.port), "Server", "SSH")}

    for service in bundle.services:
        service_name = getattr(service, "name", service.__class__.__name__)
        for port_name, port in getattr(service, "service_ports", {}).items():
            row_key = (int(port), service_name, str(port_name))
            if row_key in seen:
                continue
            seen.add(row_key)
            rows.append(
                {
                    "port_number": int(port),
                    "service": service_name,
                    "port_name": str(port_name),
                }
            )

    return sorted(rows, key=lambda row: row["port_number"])


def _collect_firewall_ports(bundle: Bundle, server: UbuntuNativeServer) -> List[int]:
    rows = _collect_firewall_port_rows(bundle, server)
    return sorted({int(row["port_number"]) for row in rows})


def _parse_firewall_open_ports(firewall_status: str | None) -> set[int] | None:
    return UbuntuTaskExecutor._parse_iptables_allowed_ports(firewall_status)


def _filter_firewall_port_rows(
    rows: List[Dict[str, Any]], open_ports: Sequence[int] | set[int] | None
) -> List[Dict[str, Any]]:
    if open_ports is None:
        return rows

    open_port_set = {int(port) for port in open_ports}
    known_ports = {int(row["port_number"]) for row in rows}
    filtered_rows = [
        row for row in rows if int(row["port_number"]) in open_port_set
    ]
    for port in sorted(open_port_set - known_ports):
        filtered_rows.append(
            {
                "port_number": port,
                "service": "Unknown",
                "port_name": "iptables rule",
            }
        )
    return filtered_rows


def _firewall_status_message(
    firewall_status: str | None,
    open_ports: set[int] | None,
    rows: List[Dict[str, Any]],
) -> str | None:
    if firewall_status is None:
        return "Could not read firewall status. Showing configured ports instead."
    if not _is_firewall_up(firewall_status):
        return "Firewall is not up. All ports are open."
    if not open_ports and not rows:
        return "No open firewall ports found."
    return None


def form_add_server(sid: str):
    id = f"form-add-server-{sid}"
    # id = f"form-add-server-{random.randint(1000, 9999)}"
    # c1, c2 = st.columns(2)
    ip = st.text_input(
        "IP Address",
        placeholder="Enter the server IP address",
        help="The IP address of the server you want to add.",
        key=f"{id}-ip",
    )
    port = st.number_input(
        "SSH Port",
        value=22,
        min_value=1,
        max_value=65535,
        step=1,
        placeholder="Enter the server SSH port",
        help="The SSH port for the server.",
        key=f"{id}-port",
    )
    root = st.text_input(
        "Root",
        value="root",
        placeholder="Enter the server root account name",
        help="Enter the server root account name.",
        key=f"{id}-root",
    )
    pw = st.text_input(
        "Password",
        placeholder="Enter the server password",
        help="The password for the server.",
        type="password",
        key=f"{id}-pw",
    )
    return ip, port, root, pw


def setup(infra: Infrastructure, config: ServiceConfig) -> Dict:
    params = dict()

    ip, port, root, pw = form_add_server(f"{len(infra.bundles) + 1}-{config.id}")

    params["${MLOX_IP}"] = ip
    params["${MLOX_PORT}"] = str(port)
    params["${MLOX_ROOT}"] = root
    params["${MLOX_ROOT_PW}"] = pw

    return params


def settings(infra: Infrastructure, bundle: Bundle, server: UbuntuNativeServer):
    if server.mlox_user:
        if server.is_debug_access_enabled or "mlox.debug" in bundle.tags:
            st.markdown("Debug access is enabled.")
            st.markdown(
                "You can access the server via SSH using the following command:"
            )
            st.markdown(f"```bash\nssh {server.mlox_user.name}@{server.ip}\n```")
            st.markdown(f"Password: `{server.mlox_user.pw}`\n")
        # st.write(f"ssh {server.mlox_user.name}@{server.ip}")
        # st.write(server.mlox_user.pw)

    if server.state != "running":
        st.markdown("Server is not running. Please start the server first.")
        return

    tab_server, tab_backend = st.tabs(["Server Info", "Backend Status"])
    with tab_server:
        st.write(server.get_server_info())

    with tab_backend:
        st.write(server.get_backend_status())
