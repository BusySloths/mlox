# Command-Line Interface

This package exposes MLOX through Typer commands.

## Structure

- `app.py`: root command and subcommand registration.
- `context.py`: project path, password, and workspace loading.
- `commands/`: project, server, service, and model commands.
- `rendering/`: terminal output helpers.

## Workflow

Each command loads one `ProjectWorkspace`, calls its public operation, renders
the returned `OperationResult`, and exits with an appropriate status.

For automation, `mlox schema` prints a versioned JSON description of the
command tree. Use the root option before the command, for example
`mlox --output json service list`, to return a JSON object with `success`,
`code`, `message`, and `data`. Domain objects are reduced to their public
identities; credential fields are redacted. Normal output remains the default.
JSON failures have a nonzero exit code and an `error` category such as
`invalid_arguments` or `operation_failed`. Set `MLOX_PROJECT_PATH` and
`MLOX_PROJECT_PASSWORD` for non-interactive project access. The CLI loads
`.env` in the current directory without replacing existing environment values;
`--project` and `--password` override them. For example,
`mlox --output json service logs otel-0.146.1 --tail 5` uses the active project.
The former positional project argument is replaced by `--project`.

Use `project inspect`, `server inspect <UUID-or-server-identifier>`, or
`service inspect <UUID-or-name>` to examine individual resources. Service and
server lists include UUIDs and capabilities; services also include their server
UUID and configured binding UUIDs. Names must be unambiguous for inspection.
Server inspection includes `ssh_username`, the account mlox uses to connect;
it is null for servers without SSH access.

For server-targeting commands such as `server exec` and `service add`, you can
use a bundle name or a unique suffix of its server address in place of the full
IP or hostname. For example, `--ip 42` selects `192.0.2.42` if no other server
address ends in `42`. Exact addresses take precedence; ambiguous names or
suffixes are rejected. Register a new server using its full address.

Run a non-interactive command on a managed SSH server through the workspace:

```sh
mlox --output json server exec --ip 192.0.2.10 --command 'docker ps'
mlox server exec --ip 192.0.2.10 --command 'systemctl status docker' --sudo --timeout 30
```

The result data contains `stdout`, `stderr`, `exit_code`, and `timed_out`.
Nonzero remote exit codes are returned as CLI exit codes; a timeout returns 124
with any captured output. The default command timeout is 60 seconds. A timeout
closes the SSH connection but cannot guarantee that remote processes stop.
Commands run through the server shell without a PTY or interactive input.
The managed SSH and sudo credentials are used without printing them; command
output itself is returned as-is. Remote commands can change server state and
do not change or automatically refresh the saved project state.

The CLI currently covers project creation, server and service lifecycle basics,
template lists, model listing and deployment. Useful workspace operations still
missing from the CLI include service/server health, service start/stop/restart,
telemetry and secret-manager binding changes, and the Operations and knowledge APIs.

## System Role

The CLI is an adapter. Keep business logic in `mlox.application` and
`mlox.project`; commands should focus on arguments, validation, and output.


## Granting SSH access

Add a client's public key to the existing managed mlox account:

```sh
mlox server add-ssh-key --ip 192.0.2.10 --public-key "$(cat client.pub)"
```

The response identifies the login username. The client can then connect using
`ssh -i ~/.ssh/id_ed25519 USERNAME@192.0.2.10` (add `-p PORT` for a custom SSH
port). They keep their private key locally; no server password is required.
This grants the same account and file access as mlox, rather than creating a
separate Linux user. Password and root login settings are unchanged.

Revoke that key with:

```sh
mlox server remove-ssh-key --ip 192.0.2.10 --public-key "$(cat client.pub)"
```

Both commands are idempotent and compare key material independently of comments.
Removal also matches entries with authorized_keys options and refuses to remove
mlox's managed access key. Revocation prevents new logins; existing SSH sessions
remain connected. These operations use the managed SSH connection and Python 3
on the server and take effect without restarting SSH. They update the remote
account, not the saved project state. The corresponding workspace methods are
`add_server_ssh_key(ip=..., public_key=...)` and
`remove_server_ssh_key(ip=..., public_key=...)`.
