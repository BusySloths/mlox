# Curated Docker applications

Memos, Etherpad, Wiki.js, and Roundcube use the same Docker service. Each has a
versioned descriptor and a bundled Compose file. The isolated Traefik instance
uses the file provider and does not mount the Docker socket. Only its assigned
HTTPS port is published. Set up the application's administrator account
immediately; application-specific signup and access settings remain the
operator's responsibility. Roundcube needs an existing IMAP/SMTP service.

These entries have Compose and unit coverage but have not yet been verified with
live containers by the implementation author. Treat them as experimental until
the deployment, backup, restore and upgrade procedures have been exercised on
the target platform. Resource estimates in the catalog are not enforced.

## TLS

The TUI asks for a TLS mode when adding an app. The CLI uses literal template
keys via `--param`, for example `--param '${APP_TLS_MODE}=managed'`. The default
is `self-signed`: Traefik presents its default certificate and browsers warn.

* `managed`: select an existing MLOX secret-manager service UUID and a secret
  name with `APP_TLS_SECRET_MANAGER_UUID` and `APP_TLS_SECRET_NAME`. The secret
  must contain string fields `tls.hostname`, `tls.crt` (PEM certificate chain),
  and `tls.key` (unencrypted PEM private key), as for the managed TLS MLflow
  Gateway. Mlox checks the hostname, validity period, and certificate/key match.
  A Cloudflare origin certificate may be used, but browsers do not trust it
  directly: traffic must pass through Cloudflare using appropriate origin TLS.
* `letsencrypt-cloudflare`: provide those same manager/name parameters, plus
  `APP_HOSTNAME` and `APP_ACME_EMAIL`. The secret must contain
  `cloudflare.api_token`, a Cloudflare DNS API token with permissions to manage
  the domain's challenge records. Traefik obtains and renews a Let's Encrypt
  certificate using DNS-01; this does not require port 80. DNS, the token's
  scope, internet access, firewall rules and public reachability remain the
  operator's responsibility. The allocated HTTPS port is in the displayed URL;
  Cloudflare's proxy supports only certain external ports.

For both non-default modes, certificate material or the DNS token is read from
the selected secret-manager service at setup. Only its reference is stored in
service configuration. The target host receives a copy in a private directory
(mode 700; individual secret files mode 600). ACME account and certificate data
are retained in the deployment's `acme` directory for renewal. To apply a rotated
managed certificate or DNS token, update the secret and run service setup again;
reconcile the containers afterwards. This is not automatic secret synchronization.

For CLI parameters, quote the literal placeholders to prevent shell expansion:

```sh
mlox service add --server-ip SERVER --template-id catalog-app-memos-0.31.0-docker \
  --param '${APP_TLS_MODE}=managed' \
  --param '${APP_TLS_SECRET_MANAGER_UUID}=MANAGER_UUID' \
  --param '${APP_TLS_SECRET_NAME}=my-certificate'
```

For Roundcube also supply `${APP_IMAP_SERVER}` and `${APP_SMTP_SERVER}` with
`ssl://` or `tls://` prefixes. `${APP_IMAP_PORT}` and `${APP_SMTP_PORT}` default
to 143 and 587; set the appropriate ports for your provider (for example, 993
for IMAP over implicit TLS). TLS certificate validation and server settings are
provided by Roundcube and the selected mail provider.

## Data and credentials

Stop and removal preserve Compose volumes and the deployment directory. The
unique directory is visible in the service configuration before removal; record
it to recover orphaned volumes and credentials. Removal does not provide a
backup, an automatic restore, or a volume deletion command. Back up application
volumes and databases with application-consistent procedures before upgrades or
removal. Re-adding an app creates a new isolated deployment and does not
reattach old data automatically.

The per-installation database/application secret derives from an automatically
generated password stored in the encrypted mlox project; the derived value is
written to `service.env` on the target in the private deployment directory. It is
not currently stored in the selected external secret manager. TLS secrets use
the selected secret manager as described above. Secure the target host and
back up the encrypted project alongside application data.

## Adding an application

Add a `mlox.catalog_app.*.yaml` descriptor beside the others, give it a
`catalog-app-` service ID, and point `build.class_name` at
`CatalogAppDockerService`, and supply a packaged Compose file with an `app`
service. Set its internal `app_port`; do not publish app or database ports.
Use named volumes and pinned image versions. Declare configuration explicitly,
provide any necessary TUI form, document authentication and backup, and add
rendering and real deployment tests. Complex initialization, non-HTTP ports,
or application integrations may require a dedicated service instead.
Regenerate the service catalogs with `python scripts/generate_service_catalog.py`.

## Integration tests

Run `uv run pytest tests/integration/test_service_catalog_apps.py -v` on a host
with Multipass and its mlox development dependencies installed. The tests create
a disposable Ubuntu VM, pull the app images, exercise HTTPS and persistence
across stop, restart, and service removal, and verify a managed certificate
through Traefik. They delete their test volumes during cleanup. They do not
exercise real Let's Encrypt issuance or require Cloudflare credentials.
