# OpenBao Usage in mlox

OpenBao is the mlox secret-manager backend for shared application and
infrastructure secrets.

## Bootstrap

When the service starts, mlox initializes and unseals OpenBao, enables KV v2 at
`secret/` by default, writes mlox policies, enables `userpass`, creates a UI
login, and creates a renewable scoped client token.

## Normal access

Use the OpenBao UI with:

- Method: `userpass`
- Username/password: shown in the mlox OpenBao settings
- Namespace: `root`

Do not use the root token for normal UI access. Root and unseal material are
recovery-only values.

## mlox secret access

mlox stores and reads secrets through the scoped client token. The exported
service secret contains only:

- OpenBao address
- scoped client token
- KV mount path
- TLS verification setting
- token renewal metadata

It does not export the root token, unseal keys, or UI password.

## External clients

A slim client only needs the OpenBao address, scoped token, mount path, and TLS
preference. It does not need the mlox infrastructure model.

Secrets are stored in KV v2 paths under:

```text
/<mount_path>/data/<secret-name>
```
