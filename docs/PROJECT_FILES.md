# Encrypted MLOX Project Files

MLOX projects are portable SQLCipher-encrypted `.mlox` databases. They contain project metadata, infrastructure, secrets, Knowledge, and Operations history. New projects no longer split encrypted `.project` metadata from infrastructure JSON in a secret manager.

## Create and open

```bash
mlox project new ./projects/demo --password 'choose-a-strong-password'
export MLOX_PROJECT_PATH="$PWD/projects/demo.mlox"
export MLOX_PROJECT_PASSWORD='choose-a-strong-password'
mlox server list
```

Creation is explicit and refuses to overwrite a file. Opening a missing project never creates one. Keep the password outside source control; `.mlox` files and SQLite sidecars are ignored by the repository.

## TUI project discovery

The TUI lists every `*.mlox` file in its current directory. A project named
`demo.mlox` uses `MLOX_PROJECT_PASSWORD_DEMO`; punctuation in the filename stem
is converted to underscores, so `team-one.mlox` uses
`MLOX_PROJECT_PASSWORD_TEAM_ONE`. Missing passwords can be entered manually.
The existing unsuffixed `MLOX_PROJECT_PATH` and `MLOX_PROJECT_PASSWORD`
variables remain supported for projects outside the current directory.

Press `P` from the dashboard to switch to another discovered project.

## Copy projects between computers

The project registry stores encrypted snapshots in `~/.mlox/project-registry`
in the SSH user's home directory on a server. A registered MLOX server name,
address, or unique address suffix uses that server's managed SSH credentials.
Both commands currently require an existing local project containing the
server; bootstrapping a first project on a new computer is not yet supported:

```bash
export MLOX_PROJECT_PATH=./sales.mlox
export MLOX_PROJECT_PASSWORD='your-project-password'
mlox project push --ip my-server
mlox project pull --ip my-server --name sales
```

`--name` selects a project by filename stem (the `.mlox` suffix is optional).
When omitted, the commands use the name from `MLOX_PROJECT_PATH` or
`MLOX_PROJECT_NAME`. Push reads that local file (or the named file in the
project directory) without opening or decrypting it; its password is not needed.
It holds a SQLite shared lock during copying and rejects files with a WAL
sidecar. Pull uses the current project's
password to load its registered servers. It writes into
`MLOX_PROJECT_DIR`, or the current directory by default, and appends `_1`,
`_2`, and so on when a filename already exists.

Push resolves the server from the current project configured by
`MLOX_PROJECT_PATH`, using that project's password from its project-specific
environment variable, `MLOX_PROJECT_PASSWORD`, or `--password`.

For pull, supply the local project and password via the environment or `--project`
and `--password`. The registry lives in the managed account's home directory.

To push a suffixed local copy back under its original registry name, specify
both the source path and registry name, for example:

```bash
mlox project push --ip my-server --project sales_1.mlox --name sales --force
```

Pushing a name already in the registry fails unless `--force` is supplied.
Force atomically replaces the registry copy without making a backup. Push and
pull are explicit snapshots, not automatic
or bidirectional synchronization: coordinate concurrent edits and pushes to avoid
replacing newer work. The project file contains the active secret-manager
configuration, but data in an external secret manager is not copied. The remote
registry does not retain project passwords. Back up the password separately.

## Python API

Use `ProjectWorkspace` for application mutations:

```python
from mlox.project import ProjectWorkspace

workspace = ProjectWorkspace.open("demo.mlox", password)
result = workspace.add_service(server_ip="10.0.0.5", template_id="postgres")
```

Direct SDK changes require an explicit commit:

```python
from mlox.project import ProjectWorkspace

workspace = ProjectWorkspace.open("demo.mlox", password)
workspace.descr = "Experiment environment"
workspace.commit()
```

`workspace.reload()` discards uncommitted in-memory changes.

## Active secret manager

Every workspace has exactly one active secret manager. New and upgraded projects
start with encrypted storage inside the `.mlox` file. An installed Tiny Secret
Manager, OpenBao, or GCP Secret Manager service can be selected later:

```python
result = workspace.set_secret_manager(service_uuid)
```

MLOX copies and verifies the current secrets before committing the new pointer.
The previous store is retained. If the selected service becomes unavailable, it
remains selected and secret operations fail rather than silently falling back to
embedded storage. Returning to embedded storage is explicit:

```python
workspace.use_embedded_secret_manager()
```

Embedded storage cannot export an application keyfile. An active secret-manager
service cannot be removed until another manager is selected.

Operations stores its optional reasoning-provider endpoint, model, and API key
in the active secret manager. A blank API-key field preserves the stored key;
the key is never returned to the TUI. The Pipeline Observer can investigate and
propose work, but is advisory-only: it never executes MLOX actions.

For OpenBao, application keyfiles are separate renewable credentials for the
same project-level KV mount, not separate per-application secret namespaces. A
secret saved in the MLOX Secret Manager tab for an OpenBao service is therefore
shared with applications that receive keyfiles for that same OpenBao service.

## Data-source model

Every project has an active data-source record. Initially it is:

```text
kind=sqlcipher, location=self
```

This means project metadata and operational data share the encrypted file. Portable SQL types, UUID identifiers, foreign keys, and repository boundaries are used so a later `kind=postgres` implementation can move operational data to PostgreSQL while the `.mlox` file remains the portable project descriptor. DuckDB is intentionally outside this first iteration.

## Encryption and concurrency

Production requires `sqlcipher3`; MLOX fails closed if the active SQLite driver does not expose SQLCipher. SQLCipher encrypts the database pages, including embedded secrets. Foreign keys, a busy timeout, full synchronous writes, rollback journaling, transactional updates, schema versions, and integrity checks improve local robustness. Close MLOX before copying a project so no temporary journal is active.

SQLCipher protects data at rest, not a running process. Anyone with the password and host access can open the project. Use OS permissions, disk backups, and password handling appropriate to the environment.

## Migrate a legacy project

```bash
python scripts/migrate_legacy_project.py \
  ./legacy.project ./projects/demo.mlox \
  --legacy-password "$OLD_PASSWORD" \
  --new-password "$NEW_PASSWORD"
```

The importer decrypts the legacy metadata, reconnects to its configured secret manager, copies infrastructure and secrets, records source provenance, validates the destination, and verifies the source digest. It never modifies the legacy file. Use `--skip-secrets` to import topology without non-infrastructure secrets.

Keep the original and its external secret store until the new project has been tested. The migration is a copy operation and is the fallback/rollback path for this release.
