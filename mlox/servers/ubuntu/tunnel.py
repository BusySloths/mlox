"""Loopback-only TCP forwarding over an existing managed SSH connection."""

from __future__ import annotations

from contextlib import contextmanager
import select
import socket
import socketserver
import threading

from mlox.tunnel import TunnelBinding, TunnelEndpoint


@contextmanager
def open_ssh_tunnel(server, endpoint: TunnelEndpoint):
    if endpoint.server_uuid != str(server.uuid):
        raise ValueError("Tunnel endpoint belongs to a different server.")
    with server.get_server_connection() as connection:
        transport = connection.transport
        if transport is None or not transport.is_active():
            raise RuntimeError("SSH transport is not connected.")
        # Check the remote endpoint and forwarding permission before reporting
        # success. The resulting test connection carries no application data.
        probe = transport.open_channel("direct-tcpip", (endpoint.remote_host, endpoint.remote_port), ("127.0.0.1", 0), timeout=15)
        if probe is None:
            raise RuntimeError("SSH server refused port forwarding.")
        probe.close()

        class Handler(socketserver.BaseRequestHandler):
            def handle(self):
                channel = None
                try:
                    channel = transport.open_channel("direct-tcpip", (endpoint.remote_host, endpoint.remote_port), self.client_address, timeout=15)
                    if channel is None:
                        return
                    while not stopped.is_set():
                        ready, _, _ = select.select((self.request, channel), (), (), 0.25)
                        for source in ready:
                            data = source.recv(65536)
                            if not data:
                                return
                            (channel if source is self.request else self.request).sendall(data)
                except (OSError, EOFError):
                    return
                finally:
                    if channel is not None:
                        channel.close()

        class Listener(socketserver.ThreadingTCPServer):
            daemon_threads = True
            allow_reuse_address = False

        stopped = threading.Event()
        with Listener(("127.0.0.1", 0), Handler) as listener:
            thread = threading.Thread(target=listener.serve_forever, daemon=True)
            thread.start()
            try:
                yield TunnelBinding(endpoint, listener.server_address[1])
            finally:
                stopped.set()
                listener.shutdown()
                thread.join()
