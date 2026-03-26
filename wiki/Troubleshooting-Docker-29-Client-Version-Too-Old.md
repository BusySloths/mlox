# Docker 29: "client version ... is too old"

> **Date:** 2025-11-26  
> **Author:** @nicococo  
> **Status:** Workaround

---

## Update

As of 2026-11-26, MLOX installs the patch automatically for new Ubuntu servers. On local macOS hosts, you still need to apply the patch manually.

---

## Summary

After upgrading Docker Engine to version 29, some services, notably Traefik, can fail with an error such as `client version 1.24 is too old`. The daemon is running, but older embedded Docker clients are rejected.

---

## Symptoms

- Traefik logs contain errors such as `Error response from daemon: client version 1.24 is too old`.
- Other services that embed older Docker clients may fail to start or keep retrying.
- The Docker daemon itself is healthy, and current `docker` CLI commands still work.
- The issue appears after upgrading to Docker Engine `29.x`.

---

## Environment

| Item | Value |
|------|-------|
| Docker version | Docker Engine 29 |
| Affected platforms | Docker Desktop on macOS, Docker Engine on Linux |
| Known affected service | Traefik |
| Tested Linux host | Ubuntu 24.04 |

---

## Root Cause

Docker Engine 29 enforces a newer minimum API version by default. Older embedded Docker clients, for example clients advertising API `1.24`, are rejected by the daemon. Lowering the daemon's minimum accepted API version restores compatibility.

---

## Solution / Workarounds

### A. macOS / Docker Desktop

1. Open **Docker Desktop**.
2. Go to **Settings** or **Preferences** -> **Docker Engine**.
3. Add or update `"min-api-version": "1.24"` in the JSON configuration.

Example:

```json
{
  "builder": {
    "gc": {
      "defaultKeepStorage": "20GB",
      "enabled": true
    }
  },
  "experimental": false,
  "min-api-version": "1.24"
}
```

4. Click **Apply & Restart**.
5. Restart affected services such as Traefik.

Notes:

- Keep the rest of your Docker Engine configuration unchanged.
- The key change is `"min-api-version": "1.24"`.

Source: <https://www.docker.com/blog/docker-engine-version-29/>

### B. Ubuntu 24.04 / systemd Docker Package

Create a systemd override for Docker:

```bash
sudo systemctl edit docker.service
```

Add:

```ini
[Service]
Environment=DOCKER_MIN_API_VERSION=1.24
```

Then restart Docker:

```bash
sudo systemctl restart docker
```

Restart affected services so they reconnect to the daemon.

Notes:

- This sets `DOCKER_MIN_API_VERSION=1.24` for the Docker daemon process.
- Other Linux distributions or packaging styles may require a different override path or service definition.

Source: <https://github.com/traefik/traefik/issues/12253#issuecomment-3515555316>

---

## Verification

- Traefik logs no longer show the `client version ... is too old` error.
- Services that previously failed can connect to Docker and operate normally.
- If needed, confirm by restarting the affected service and reviewing its logs.

---

## Caveats and Recommendations

- Lowering the minimum API version improves compatibility but keeps support for older client behavior enabled.
- Prefer upgrading the affected client or service to a newer Docker API when possible.

---

## Related

- [Traefik issue #12253](https://github.com/traefik/traefik/issues/12253)
- [Docker Engine version 29 announcement](https://www.docker.com/blog/docker-engine-version-29/)
- [Traefik issue comment with Ubuntu override example](https://github.com/traefik/traefik/issues/12253#issuecomment-3515555316)

---

## See Also

- [Troubleshooting](Troubleshooting) — Troubleshooting index
- [Installation](Installation) — Local Docker setup basics
