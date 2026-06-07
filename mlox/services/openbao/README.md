# OpenBao Service

OpenBao is the mlox secret-manager service for storing application and
infrastructure secrets. It provides a Vault-compatible API, a browser UI, and a
KV v2 secrets engine mounted at the configured `mount_path` (`secret` by
default).

## Production Baseline

The service runs OpenBao `2.5.4` in server mode with persistent integrated Raft
storage. This replaced the previous `server -dev` setup, which was unsuitable
for production because dev mode auto-initializes, auto-unseals, and does not use
durable storage.

The mlox OpenBao stack now uses:

- OpenBao native HTTPS on the mapped service port.
- A generated `openbao.hcl` mounted read-only into the container.
- Integrated Raft storage at `/openbao/data`.
- Persistent host bind mounts for `data`, `logs`, config, and TLS material.
- mlox-managed initialization, unseal keys, and root token storage.
- KV v2 enabled at the configured mount path.
- mlox-scoped policies, userpass UI login, and renewable client token.
- File audit logging at `/openbao/logs/audit.log`.

The Docker compose stack intentionally exposes OpenBao directly over HTTPS. It
does not run a Traefik sidecar for this service.

## Runtime Files

During setup, mlox writes the stack into:

```text
${MLOX_USER_HOME}/openbao-2.5.4
```

The runtime directory contains:

```text
config/openbao.hcl
data/
logs/
cert.pem
key.pem
service.env
docker-compose-openbao.yaml
```

The generated OpenBao config includes:

- `storage "raft"` with `path = "/openbao/data"`
- `listener "tcp"` on `0.0.0.0:8200`
- TLS enabled with `/openbao/tls/cert.pem` and `/openbao/tls/key.pem`
- `api_addr = "https://<server-host>:<mapped-port>"`
- `cluster_addr = "http://openbao:8201"`
- `ui = true`
- `disable_mlock = true`
- file audit logging at `/openbao/logs/audit.log` via declarative
  `audit "file" "file"` configuration

## Bootstrap Flow

When the service starts, mlox waits for OpenBao to report health via the
container-local `bao` CLI. It then performs bootstrap:

1. If OpenBao is uninitialized, mlox runs `bao operator init`.
2. mlox stores the returned root token and unseal key in the service state.
3. If OpenBao is sealed, mlox submits stored unseal keys.
4. mlox ensures KV v2 exists at `mount_path`.
5. mlox writes least-privilege mlox policies.
6. mlox enables userpass and creates UI login credentials.
7. mlox creates a renewable scoped client token for secret-manager access.

File audit logging is configured before startup in `openbao.hcl`. OpenBao no
longer allows normal API-created audit devices in this runtime mode.

The default bootstrap uses one key share and a threshold of one:

```text
key_shares = 1
key_threshold = 1
```

This is practical for a single-node mlox-managed service. Operators should still
backup the root token and unseal key outside mlox for recovery.

## Using The Service In mlox

After setup, open the service settings panel in the mlox Services page.

The OpenBao settings panel shows:

- initialization status
- seal status
- userpass UI login credentials
- scoped mlox client token status
- token renewal and rotation actions
- emergency-only root token reveal
- unseal key count and optional emergency reveal
- an `Unseal` button when OpenBao is sealed
- the KV secret list when OpenBao is initialized and unsealed

Use the generated userpass credentials for the OpenBao browser UI. Use the root
token only for recovery or bootstrap administration. The namespace is `root`.

The downloadable secret-manager keyfile contains only a scoped mlox API token
and connection metadata. It does not contain the root token, unseal keys, or UI
password. For OpenBao, keyfiles are generated for named applications. mlox stores
only each application's token accessor and metadata, so the root-backed UI can
renew or revoke that application's credential without storing the token value.

Secrets can be added, listed, and read directly from the mlox UI. The client uses
KV v2 paths, so a secret named `example` is written to:

```text
/v1/<mount_path>/data/example
```

and listed via:

```text
/v1/<mount_path>/metadata
```

## Browser UI

The OpenBao UI is available at the service URL shown by mlox:

```text
https://<server-ip-or-host>:<mapped-port>
```

mlox generates self-signed TLS material for the service. Browsers may require
accepting the certificate warning unless the generated certificate is trusted by
the client machine.

Login with:

```text
Method: userpass
Username: <mlox admin username shown in settings>
Password: <mlox admin password shown in settings>
Namespace: root
```

Root token login remains available only as emergency recovery material.

## Seal And Unseal

OpenBao starts sealed after initialization and after restarts unless an auto
unseal mechanism is configured. This service currently uses manual Shamir
unseal, managed by mlox.

If OpenBao is sealed:

- the API will not serve normal secret operations
- mlox will show the service as not ready for secret access
- the settings panel displays an `Unseal` button when stored unseal keys exist

Use the `Unseal` button to submit the stored key material. On normal `Resume`,
mlox also attempts to unseal automatically using the stored key.

## Persistence And Stop Behavior

Raft data is stored in the service runtime `data/` directory. Normal pause/stop
keeps this data. Teardown removes the target runtime directory and is destructive
by design.

This means:

- pausing and resuming preserves secrets
- restarting the container preserves secrets
- teardown deletes the OpenBao data unless it has been backed up elsewhere

## TLS Notes

External access is HTTPS. Bootstrap commands run inside the OpenBao container
using:

```text
BAO_ADDR=https://127.0.0.1:8200
BAO_SKIP_VERIFY=true
```

`BAO_SKIP_VERIFY` is used only because the generated certificate is self-signed
and the bootstrap call is container-local. mlox clients also default
`verify_tls=False` for the same reason.

## Operational Notes

- Keep the root token and unseal key backed up outside mlox.
- Use the generated userpass credentials and scoped client token for day-to-day
  access instead of the root token.
- Application keyfile tokens are periodic renewable tokens. They can keep
  running indefinitely if they are renewed before each selected period expires.
- If a keyfile token expires, API calls made with that keyfile fail with
  OpenBao's token-expired/permission error. Rotate and download a new keyfile.
- Rotating the service token does not update already downloaded keyfiles because
  each keyfile contains its own token string.
- Do not use teardown unless deleting the OpenBao data is intended.
- Future production hardening can add HA Raft peers, KMS auto-unseal, trusted
  certificates, and least-privilege OpenBao policies.
