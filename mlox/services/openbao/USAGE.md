# OpenBao Usage

OpenBao is the mlox secret-manager backend for shared application and
infrastructure secrets.

## Bootstrap

When the service starts, mlox initializes and unseals OpenBao, enables KV v2 at
`secret/` by default, writes mlox policies, enables `userpass`, creates a UI
login, and creates a renewable scoped client token.

## Browser access

Use the OpenBao UI with:

- Method: `userpass`
- Username/password: shown in the mlox OpenBao settings
- Namespace: `root`

Do not use the root token for normal UI access. Root and unseal material are
recovery-only values.

## mlox access

mlox stores and reads secrets through the scoped client token. The exported
service secret contains only:

- OpenBao address
- scoped client token
- KV mount path
- TLS verification setting
- token renewal metadata

It does not export the root token, unseal keys, or UI password.

If the mlox service token expires, rotate it in the Access tab. Rotation creates
and saves a fresh scoped token using the root-backed admin path.

## Application credentials

Use one named credential per application, for example `training-worker` or
`feature-store-sync`.

- Add the application in the Applications tab and choose a renewal period.
- Use `Renew` before the selected period expires.
- Use `Revoke` when an application should lose access.
- Use `Rotate keyfile` only when the application needs a new downloadable token.

mlox stores the token accessor and metadata, not the token value. The accessor
allows root-backed lookup, renewal, and revocation without granting secret
access.

Application credentials are periodic renewable tokens. They can run indefinitely
only if the application renews them before each selected period expires.

## External clients

A slim client only needs the OpenBao address, scoped token, mount path, and TLS
preference. It does not need the mlox infrastructure model.

Secrets are stored in KV v2 paths under:

```text
/<mount_path>/data/<secret-name>
```

If a downloaded application token expires, renew it from the application before
expiry or rotate and download a new keyfile from mlox.
