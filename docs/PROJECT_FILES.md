# Encrypted MLOX Project Files

MLOX projects are single, portable `.mlox` databases encrypted by SQLCipher. A project file contains project metadata, the active data-source descriptor, infrastructure state, and project secrets. The old split between an encrypted `.project` metadata document and infrastructure JSON in a secret manager is no longer used for newly created projects.

## Create and open

```bash
mlox project new ./projects/demo --password 'choose-a-strong-password'
export MLOX_PROJECT_PATH="$PWD/projects/demo.mlox"
export MLOX_PROJECT_PASSWORD='choose-a-strong-password'
mlox server list
```

Creation is explicit and refuses to overwrite a file. Opening a missing project never creates one. Keep the password outside source control; `.mlox` files and SQLite sidecars are ignored by the repository.

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
