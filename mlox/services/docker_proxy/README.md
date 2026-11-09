# Docker reverse proxy

An independent Traefik service that publishes ports 80 and 443, obtains optional
Let's Encrypt certificates, and routes public hostnames to existing HTTP(S)
endpoints. It does not reconfigure, stop, or remove backend services. Traefik
uses the file provider and does not mount the Docker socket. One proxy should
normally run per server. Port 80 or 443 must be available before setup; notably,
existing catalog apps using their own Let's Encrypt HTTP challenge already use
port 80. Stop or reconfigure those explicitly before starting this proxy.
If setup reports an occupied port, inspect the listeners and published Docker
ports on the server with:

```sh
sudo ss -ltnp '( sport = :80 or sport = :443 )'
sudo docker ps --format 'table {{.Names}}\t{{.Ports}}'
```

Do not stop a listener until you know which service it supports. The gateway
requires both ports; a different HTTPS port would not provide the same standard
domain access. The HTTP-01 Let's Encrypt challenge also requires public port 80.

Add **Traefik Gateway** to the Docker server in the TUI and set it up. Its
service settings panel lists routes and lets you add or remove them live. The
CLI offers `mlox service proxy-routes`, `proxy-route-add`, and
`proxy-route-remove` (use `--help` for options). Route additions reject a
hostname already present; remove the old route before replacing it. Removing a
route does not stop its backend. Removing or stopping the proxy leaves existing
applications and their published ports unchanged. The proxy deployment directory,
including ACME account data and any managed certificate copies, is retained on
removal so certificates are not lost accidentally.

Optionally select a relayed app in the route form to populate an editable backend
URL and Host override from its app contract. The CLI also accepts
`--service-uuid`; when `--backend` is omitted it derives the endpoint from the
selected app. An explicitly supplied backend is preserved and is not verified
against the linked service. Apps without a known endpoint, such as some Compose
repository deployments, require a manually entered backend. The resulting
association groups the app under the proxy in the Apps tab. Older routes without
a service UUID are matched only when their local backend port identifies one app
unambiguously.

The endpoint is a suggestion, not a connectivity test. The default contract uses
the direct UI URL and rewrites the host to `host.docker.internal` for a
host-published service on the same server, or to the app server's address for a
remote service reporting localhost. Services can override the contract for their
own networks. Check that the backend is actually bound to a reachable interface,
that firewall rules allow the proxy, and that it accepts the requested Host
header. Apps with path-based UIs retain their path in Apps tab links; the proxy
does not rewrite paths or public URLs.

Example for an existing Memos instance running on the same server:

```sh
mlox service proxy-route-add --name docker-proxy --hostname notes.example.org \
  --backend https://host.docker.internal:5230 --backend-host SERVER_IP \
  --tls-mode letsencrypt --insecure-backend
mlox service proxy-routes --name docker-proxy
mlox service proxy-route-remove --name docker-proxy --hostname notes.example.org
```

Replace the port and backend Host header with the actual endpoint values. The
special hostname `host.docker.internal` resolves to the Docker host gateway;
`localhost` inside Traefik means the proxy container and is rejected. The
backend Host override is necessary when an existing app proxy expects a different
Host header than the public hostname. Applications may still need their own
trusted-proxy/public-URL settings for redirects and cookies; this service does
not change those settings.

A route's public TLS mode is `self-signed`, `letsencrypt`, or `managed`.
Let's Encrypt HTTP-01 requires public DNS pointing to the server and inbound
port 80. Certificates are requested and renewed asynchronously, so initial
requests may see the default certificate until issuance succeeds. `managed`
uses `--tls-secret-manager-uuid` and `--tls-secret-name` for the same structured
secret as the managed MLflow gateway: `tls.hostname`, `tls.crt`, and `tls.key`.
The hostname must match the route. Certificate and key are validated before
configuration is changed, and PEM copies are stored in the private deployment
directory. To apply a rotated certificate, remove and re-add the route. Old
certificate copies remain in the protected directory; remove them deliberately
when no longer needed. Certificate trust and endpoint health are independent.

Backend HTTPS certificate verification is **on by default**. Existing app
Traefik default certificates are self-signed and cannot usually be verified by
the proxy. `--insecure-backend` disables chain and hostname verification only
for that route; the hop stays encrypted but its peer is not authenticated. Use
it only when you accept that trade-off. Backend certificate trust configuration
is not yet supported. Restrict direct access to backend ports with Docker-aware
firewall rules if needed, and verify that proxy-to-backend traffic still works.

Route configuration is persisted in the encrypted project and rendered to a
watched file via atomic rename. Managed certificate values and private keys are
not saved in route state. If a project commit fails after a route update, mlox
attempts to restore the previous runtime configuration and reports rollback
failure if it cannot. In an unclean process or host failure, rerun proxy setup
to reconcile runtime configuration from saved project state. Do not edit the
managed routing file by hand. No administrative HTTP dashboard is published.

The proxy's health check reports its container state; use the proxy logs and
an HTTPS request to verify individual routes and certificate issuance. This
initial service is experimental: run the dedicated Multipass integration test
on a disposable server with `uv run pytest tests/integration/test_service_docker_proxy.py -v`.
It covers self-signed forwarding and live route removal, but live public ACME
issuance needs separate DNS and network validation.
