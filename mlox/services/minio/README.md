# MinIO image

The standalone MinIO stack and Milvus's MinIO dependency build
`mlox-minio:RELEASE.2025-07-23T15-54-02Z` locally on the target Docker server.
The former Docker Hub images are unavailable, and the corresponding official
Quay images could not be pulled during verification.

The bundled Dockerfile checks out the official MinIO release and verifies commit
`7ced9663e6a791fef9dc6be798ff24cda9c730ac` before compiling it. It retains the
upstream entrypoint and the existing data and certificate paths. The Go build
supports native ARM64 and AMD64 targets; AMD64 uses the baseline v1 instruction set.

Service setup copies the Dockerfile into `minio-build/` next to the deployed
Compose file. Compose builds it automatically. The first deployment needs access
to Docker Hub's Go/Debian base images, GitHub, Debian packages, and Go modules and
takes longer than pulling a prebuilt image. Later builds reuse Docker's cache.

The standalone service keeps its July 2025 release. Milvus now uses that same
pinned release instead of an unpinned `latest` image. Existing data volumes and
credentials are unchanged.

## Certificates and bucket browser

The MinIO service settings show the certificate stored in the project and offer
read-only bucket and object listing. New deployments use a self-signed certificate
valid for 3650 days. Existing certificates keep their original expiry until renewed.

**Renew Certificate** creates a replacement for the configured API hostname or IP,
recreates the container without deleting its data volume, verifies an authenticated
bucket request, and saves the new certificate in the project. If activation or
verification fails, it attempts to restore the old pair and recreate the container.
A private `.tls-rotation-*` directory on the server retains the old pair for recovery;
protect and remove old backups when no longer needed. The client machine running
mlox must be able to reach the MinIO API for verification.

Renewal changes the self-signed certificate that clients trust. Select each secret
manager used by clients and run **Collect Service Secrets** after renewal, including
for dependent services such as DuckLake. Restart or reconnect clients that have
cached the old certificate. Other copies of the certificate must also be updated.
The project certificate shown in the panel is not a live inspection of the server.
