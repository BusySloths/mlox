from contextlib import contextmanager
import socket
import socketserver
import threading
from types import SimpleNamespace

from mlox.servers.ubuntu.tunnel import open_ssh_tunnel
from mlox.tunnel import TunnelEndpoint


def test_tunnel_forwards_and_releases_loopback_port():
    class Echo(socketserver.BaseRequestHandler):
        def handle(self):
            data = self.request.recv(1024)
            if data:
                self.request.sendall(data)

    with socketserver.TCPServer(("127.0.0.1", 0), Echo) as target:
        thread = threading.Thread(target=target.serve_forever, daemon=True)
        thread.start()

        class Transport:
            def is_active(self):
                return True

            def open_channel(self, kind, destination, origin, *, timeout):
                assert kind == "direct-tcpip"
                assert timeout == 15
                return socket.create_connection(destination, timeout=2)

        @contextmanager
        def connection():
            yield SimpleNamespace(transport=Transport())

        server = SimpleNamespace(uuid="server", get_server_connection=connection)
        endpoint = TunnelEndpoint("service", "db", "server", "127.0.0.1", target.server_address[1])
        try:
            with open_ssh_tunnel(server, endpoint) as binding:
                with socket.create_connection((binding.local_host, binding.local_port), timeout=2) as client:
                    client.sendall(b"hello")
                    assert client.recv(5) == b"hello"
            with socket.socket() as check:
                check.settimeout(1)
                assert check.connect_ex((binding.local_host, binding.local_port)) != 0
        finally:
            target.shutdown()
            thread.join()
