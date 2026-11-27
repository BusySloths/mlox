# DuckLake connector integration test

Run from the repository root:

```sh
task tests:integration:run -- -k ducklake
```

The task selects the `dev` and `ducklake` extras through `uv run`, which
installs DuckDB and the integration-test dependencies automatically. Multipass must be installed and its daemon running, as for the
other VM integration tests. The host must reach the VM's published PostgreSQL
and MinIO ports and the DuckDB extension repository.

The fixture uses `ubuntu_docker_server` to launch the suite's disposable
Multipass VM and configure Docker. It installs the standard MLOX PostgreSQL 16
and MinIO services with `add_service` and `prepare_service`, waits for readiness,
and creates a unique database, metadata schema and S3 bucket/prefix. No service
JSON environment variables or manually provisioned services are needed.

Both services export their generated certificates. Bucket setup uses MinIO's
exported CA, and DuckLake clients receive certificates through the normal
service-secret collector and temporary embedded project secret manager. The
roundtrip exercises TLS, explicit initialization, writes, appends, reads, health,
fresh-client reconnection, recollection after an endpoint representation change,
and replacement-connector recovery without calling `create_lake` again.

Finalizers are registered before service setup so partial failures trigger
cleanup. They remove connectors, delete test bucket objects and the bucket,
close the S3 client, and tear down MinIO and PostgreSQL including their volumes.
The shared server/VM fixtures perform their usual final Docker cleanup and VM
deletion; the temporary embedded secret database belongs to pytest's temporary
directory. Removing the original connector during recovery leaves PostgreSQL
metadata and MinIO objects intact until the fixture's final cleanup.

Without `--run-integration` (or `RUN_INTEGRATION=1`) the test is skipped. Missing
optional Python dependencies also cause a skip before the VM is allocated.
Configured services that fail readiness or DuckDB extension installation fail
the test.
