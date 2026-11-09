# Create and use a DuckLake

MLOX's DuckLake connector brings together an existing PostgreSQL database and
S3-compatible object storage. PostgreSQL holds the catalog metadata, while the
bucket holds data files. DuckDB runs in each client process; the connector does
not deploy a query server.

## Before you start

You need running PostgreSQL, S3-compatible storage (such as MinIO) registered in MLOX, plus an existing
bucket. A secret manager is optional and can distribute connection details to
remote clients. The PostgreSQL user
must be able to create the lake's metadata schema and tables. Client machines
must be able to reach the exported PostgreSQL and S3 endpoints and the DuckDB
extension repository; remote clients using a collected secret must also reach
the secret manager.

Install the client on each machine that will query the lake:

```sh
pip install 'busysloths-mlox[ducklake]'
```

## Add the connector

In the MLOX TUI, add a DuckLake service to a virtual connector backend. Enter a
lake name, select the PostgreSQL and S3 storage services, and enter the name
of the existing bucket. Then set up the service.

For example, a lake named `sales` in a bucket named `analytics` gets:

| Purpose | Derived value |
| --- | --- |
| DuckDB catalog | `sales` |
| PostgreSQL metadata schema | `ducklake_sales` |
| S3 data prefix | `s3://analytics/ducklake/sales/` |
| Collected secret key | DuckLake service UUID |

The name must start with a letter and use only letters, digits and underscores.
Choose a name whose metadata schema is not already used by another lake. You
can use the same PostgreSQL database and bucket for multiple lakes with distinct
names. Setup does not create or check the bucket.

DuckLake exports connection information directly from the selected services via
`get_secrets()`. To distribute these details, select a manager in the
secret-manager panel and use **Collect service secrets**. The collector
stores the complete DuckLake connection under the DuckLake service UUID. It
includes catalog settings, endpoints, credentials and exported certificates;
separately collected PostgreSQL and S3 secrets are not required by the client.
Restrict access to the collected secret: the exported MinIO credentials
currently have root privileges.

## Initialize and query the lake

For a remote client, obtain a configured `secret_manager`, then load the
connection details using the DuckLake service UUID:

```python
from mlox.services.ducklake.client import DuckLakeClient

client = DuckLakeClient.from_secret(secret_manager, "<ducklake-service-uuid>")

# Run once to initialize the catalog. Regular connections do not create it.
client.create_lake()

with client.connect() as connection:
    connection.execute("CREATE TABLE IF NOT EXISTS orders (id INTEGER, amount DOUBLE)")
    connection.execute("INSERT INTO orders VALUES (?, ?)", [1, 42.5])

print(client.query("SELECT * FROM orders"))
print(client.list_tables())
```

Alternatively, when you have the connector service and infrastructure in
Python, use `service.get_client(infra)`; it obtains current connection details
directly from the selected services and does not require a secret manager. Catalog initialization is separate from
service setup. `create_lake()` can attach an existing catalog if its data path
matches, so use a distinct lake name when creating a new lake.

## Maintain access and data

Collected secrets are snapshots. After rotating credentials or changing
endpoints, run **Collect service secrets** again for the manager used by remote clients. This
updates the stored entries for all collected services, including DuckLake.
Clients load credentials on each new connection. Exported certificates are kept
in private temporary files until the connection closes. Removing the connector
does not delete the collected secret, catalog or data files.

Back up PostgreSQL and object storage together; some data may be inlined in
PostgreSQL. The [connector reference](../mlox/services/ducklake/README.md) covers
client methods, compatibility with older connectors, health checks and
maintenance links.
