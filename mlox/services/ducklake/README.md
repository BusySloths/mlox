# DuckLake connector

This connector registers a DuckLake backed by an existing PostgreSQL database
and an S3-compatible bucket. DuckDB runs in each client process; it is not a
server. Install the client on every machine that uses it:

```sh
pip install 'busysloths-mlox[ducklake]'
```

DuckLake 1.1 requires DuckDB 2.0. The client installs and loads the DuckDB
`ducklake`, `postgres`, and `httpfs` extensions on first use. The client machine
must reach the extension repository, PostgreSQL, S3 and the secret manager.
The PostgreSQL database and S3 bucket must already exist. Choose a unique
PostgreSQL metadata schema and an S3 bucket/prefix for each lake. The initial
catalog user needs permission to create the metadata schema and its tables;
regular readers and writers can use narrower permissions.

Add the connector to a virtual connector backend and select the PostgreSQL,
S3-compatible object storage and secret-manager services in the TUI. Services
that advertise the `s3_object_storage` capability can be selected. Enter a data path such
as `s3://my-bucket/my-lake/`, metadata schema (default `ducklake`), catalog
name (default `lake`), and two existing secret names. CLI users can supply the
same template parameters with `service add`; see `mlox service add --help`.

Secrets exported by MLOX `get_secrets()` are also accepted in their nested
`postgres_connection`, `s3_connection` and legacy `minio_root_credentials` form. For MinIO using a
self-signed certificate, save the exported certificate as a PEM file on the
client and provide its path as `ca_cert_file`.

The PostgreSQL secret is a dictionary with `username` and `password`; it can
also specify `host`, `port`, `database`, `sslmode`, and `sslrootcert` (a certificate file on the client). The S3 secret has `access_key`
and `secret_key` (or MinIO's `username` and `password`) and may specify
`endpoint` (for example `https://minio.example:9000`), `region`, `url_style`
(`path` or `vhost`), `session_token`, and `ca_cert_file` (a trusted CA file on the client, needed for a self-signed MinIO certificate). Endpoint, database and port defaults
are taken from the selected PostgreSQL and MinIO services when available;
secret fields override them for client-specific network addresses. For other
object storage connectors specify the endpoint in the secret. TLS is enabled
for HTTPS endpoints. Credentials are loaded anew for each connection and passed
to temporary DuckDB secrets; they are not persisted in the connector.

```python
# `service` is the DuckLakeService from the MLOX infrastructure.
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

The selected service UUIDs identify and validate the MLOX dependencies. Secret
references are independent of those services, so verify that their endpoint
overrides refer to the intended instances. MLOX setup registers the connector;
it does not initialize or probe the lake, and removing the connector does not
delete the catalog, bucket, files, or secrets. Health probes require permission
to list the configured S3 prefix; restricted read-only roles without list
permission may report unknown even when they can read a known object.

Back up PostgreSQL and object storage as one lake. Inlined data may exist only
in PostgreSQL. Plan snapshot retention and compaction explicitly; this connector
does not schedule cleanup or delete old files. See the upstream [backup and
recovery guide](https://ducklake.select/docs/stable/duckdb/guides/backups_and_recovery)
and [maintenance guide](https://ducklake.select/docs/stable/duckdb/maintenance/recommended_maintenance).
