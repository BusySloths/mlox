# Build the existing service release without depending on MinIO's image registries.
FROM golang:1.24.6-bookworm AS build
WORKDIR /src/minio
RUN git clone --depth 1 --branch RELEASE.2025-07-23T15-54-02Z \
        https://github.com/minio/minio.git . \
    && test "$(git rev-parse HEAD)" = "7ced9663e6a791fef9dc6be798ff24cda9c730ac"
RUN CGO_ENABLED=0 GOAMD64=v1 go build -tags kqueue -trimpath \
    -ldflags "$(MINIO_RELEASE=RELEASE go run buildscripts/gen-ldflags.go 2025-07-23T15:54:02Z)" \
    -o /out/minio .

FROM debian:bookworm-slim
RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates \
    && rm -rf /var/lib/apt/lists/*
ENV HOME=/root
COPY --from=build /out/minio /usr/bin/minio
COPY --from=build --chmod=755 /src/minio/dockerscripts/docker-entrypoint.sh /usr/bin/docker-entrypoint.sh
COPY --from=build /src/minio/LICENSE /licenses/minio/LICENSE
LABEL org.opencontainers.image.source="https://github.com/minio/minio" \
      org.opencontainers.image.revision="7ced9663e6a791fef9dc6be798ff24cda9c730ac" \
      org.opencontainers.image.version="RELEASE.2025-07-23T15-54-02Z"
EXPOSE 9000 9001
VOLUME ["/data"]
ENTRYPOINT ["/usr/bin/docker-entrypoint.sh"]
CMD ["minio"]
