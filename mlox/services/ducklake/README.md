# DuckLake connector

For a walkthrough of setup and first queries, see the [DuckLake guide](../../../docs/DUCKLAKE.md).

This connector registers a DuckLake backed by an existing PostgreSQL database
and an S3-compatible bucket. DuckDB runs in each client process; it is not a
server. Install the client on every machine that uses it:

```sh
pip install 'busysloths-mlox[ducklake]'
```

DuckLake 1.1 requires DuckDB 2.0. The client installs and loads the DuckDB
`ducklake`, `postgres`, and `httpfs` extensions on first use. The client machine
must reach the extension repository, PostgreSQL and S3. Remote clients loading
a collected secret also need access to its secret manager.
The PostgreSQL database and S3 bucket must already exist. Choose a unique
PostgreSQL metadata schema and an S3 bucket/prefix for each lake. The initial
catalog user needs permission to create the metadata schema and its tables;
regular readers and writers can use narrower permissions.

Add the connector to a virtual connector backend. In the TUI, enter a lake
name, select the existing PostgreSQL and S3-compatible storage services, and
enter an existing S3 bucket name. For a lake named `sales`, MLOX
derives catalog `sales`, metadata schema `ducklake_sales` and data path
`s3://<bucket>/ducklake/sales/`. Choose a name that is not already used for a
lake in the PostgreSQL database.

To distribute connection details to remote clients, use **Collect service
secrets** in a secret manager.
DuckLake's `get_secrets()` reads the selected services' exports and returns a
complete connection. The collector stores it under the DuckLake service UUID;
no separate PostgreSQL or S3 secrets are needed for the client. Recollect after
credentials or endpoints change. Collection updates all collected service
entries in that manager. The bucket and services must already exist; setup does
not create or check the bucket. The stored credentials may be privileged
(MinIO currently exports its root credentials), so restrict access.

A client on another machine can use the secret manager and DuckLake service UUID:

```python
from mlox.services.ducklake.client import DuckLakeClient

client = DuckLakeClient.from_secret(secret_manager, "<ducklake-service-uuid>")
```

The client loads credentials for each connection. Exported PEM certificates
are written to private temporary files for the lifetime of a connection and
removed on close; close connections promptly. Existing connectors with separate
PostgreSQL and S3 secret names continue to work. Those secrets may use the
nested `postgres_connection`, `s3_connection`, or legacy
`minio_root_credentials` format, or contain connection fields directly.

```python
# `service` is the DuckLakeService from the MLOX infrastructure.
# This obtains live credentials from the services without a secret manager.
client = service.get_client(infra)

# Explicit one-time initialization; ordinary connections never create a lake.
client.create_lake()

with client.connect() as con:
    con.execute('CREATE TABLE IF NOT EXISTS measurements (id INTEGER, value DOUBLE)')
    con.execute('INSERT INTO measurements VALUES (?, ?)', [1, 3.14])

rows = client.query('SELECT * FROM measurements WHERE id = ?', [1])
frame = client.read_dataframe('SELECT * FROM measurements')  # requires pandas
tables = client.list_tables()
status = client.check()  # read-only catalog access and S3 prefix listing
```

`write_dataframe(table, dataframe, schema="main", mode="create")` creates a
table from a supported DuckDB dataframe; `append` and `replace` are also
available. Use `connect()` for transactions, advanced SQL, snapshot queries,
and explicit DuckLake maintenance. Close connections when done. Attaching an
existing lake fails if its recorded data path differs from the configured one.
Creation is opt-in and does not implicitly migrate existing catalogs.

MLOX setup registers the connector but does not initialize or probe the lake. `create_lake()` is still explicit and can attach an existing catalog if
its data path matches; choose a unique metadata schema for each new lake. Health probes require permission
to list the configured S3 prefix; restricted read-only roles without list
permission may report unknown even when they can read a known object.

Back up PostgreSQL and object storage as one lake. Inlined data may exist only
in PostgreSQL. Plan snapshot retention and compaction explicitly; this connector
does not schedule cleanup or delete old files. See the upstream [backup and
recovery guide](https://ducklake.select/docs/stable/duckdb/guides/backups_and_recovery)
and [maintenance guide](https://ducklake.select/docs/stable/duckdb/maintenance/recommended_maintenance).
