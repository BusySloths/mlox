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
