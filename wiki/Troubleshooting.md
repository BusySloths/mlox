# Troubleshooting

Known issues, workarounds, and environment-specific fixes for MLOX and its dependencies.

---

## Contents

1. [VM — Multipass — macOS (OSX 26) — Not Reachable After Spin Up](#vm--multipass--macos-osx-26--not-reachable-after-spin-up)
2. [Docker 29 — "client version … is too old"](#docker-29--client-version--is-too-old)

---

## VM — Multipass — macOS (OSX 26) — Not Reachable After Spin Up

**Date:** 2025-11-23 · **Author:** @nicococo · **Status:** Fixed

### Update

> ⚠️ Don't forget to also add your browser and Multipass to the Local Network permission list for any app that needs to connect to services running on MLOX VMs (e.g. MLflow UI, Jupyter).  
> ⚠️ Also check your local firewall settings — macOS firewall can block inbound connections even when Local Network permission is granted.

### Summary

Multipass VM starts but is not reachable from the host (Terminal / VS Code) on macOS "OSX 26" due to macOS privacy settings blocking local network access for the app used to launch or communicate with the VM.

### Symptoms

- Multipass instance appears as running (`multipass list`) but `multipass shell` / SSH / ping fail or hang.
- VS Code Remote / Remote-SSH cannot connect to the instance.
- `ping <vm-ip>` from host times out or returns "no route to host."
- No obvious errors in Multipass logs indicating a networking failure on the Multipass side.

### Environment

| Item | Detail |
|------|--------|
| Host OS | macOS OSX 26 |
| VM manager | Multipass |
| Apps affected | Terminal.app, iTerm, VS Code (Remote extensions) |
| Network | Default Multipass networking |

### Steps to Reproduce

```bash
# 1. Launch a new instance
multipass launch --name test-vm

# 2. Confirm it is running
multipass list

# 3. Try to connect — this hangs or fails
multipass shell test-vm
```

### Root Cause

macOS privacy settings can block an app (Terminal, iTerm, or VS Code) from communicating with local network devices. When the terminal/editor does not have permission to **"Find and communicate with local devices,"** it cannot reach Multipass-hosted VMs on the host's local network interface.

### Solution / Workaround

1. Open **System Settings** on macOS.
2. Go to **Privacy & Security → Local Network**.
3. Find and **enable** the app you use to access the VM:
   - **Terminal.app** (built-in macOS Terminal)
   - **iTerm** (if using iTerm2)
   - **Visual Studio Code** (if connecting from VS Code)
   - Any **browser** used to access services deployed on the VM (e.g. MLflow UI)
4. After toggling the permission, **quit and re-open** the app.
5. _(If needed)_ Restart the Multipass instance:

```bash
multipass stop <instance-name>
multipass start <instance-name>
```

6. Re-attempt connection:

```bash
multipass shell <instance-name>
```

### Verification

- `multipass shell <instance-name>` successfully opens a shell.
- `ping <vm-ip>` from the host returns responses.
- VS Code Remote connects successfully and opens a workspace inside the VM.

### Notes

- If you use multiple terminals/editors, ensure **each one** has Local Network permission.
- On first toggle, macOS may prompt you; enable the permission and restart the app.
- If issues persist after granting permission and restarting, try restarting the Multipass service or rebooting the host as a last resort.

---

## Docker 29 — "client version … is too old"

**Date:** 2025-11-26 · **Author:** @nicococo · **Status:** Workaround

### Update

> ✅ As of **2026-11-26**, MLOX automatically applies the patch for **new Ubuntu servers**.  
> For **localhost macOS** you still need to apply the patch manually (see Option A below).

### Summary

After upgrading Docker Engine to version 29, some services (notably Traefik) report:

```
Error response from daemon: client version 1.24 is too old.
Minimum supported API version is 1.44, please upgrade your client...
```

This prevents those services from talking to the Docker daemon even though the daemon is running.

### Symptoms

- Traefik logs show errors such as:  
  `"Failed to retrieve information of the docker client and server host error=\"Error response from daemon: client version 1.24 is too old...\""`
- Other Docker-client-based services may fail to start or repeatedly retry with similar API-version errors.
- The Docker daemon itself is running; `docker` CLI operations (which use the current client) work, but older embedded clients (in third-party binaries/containers) fail.
- Observed after upgrading Docker Engine to **v29.x**.

### Environment

| Item | Detail |
|------|--------|
| Affected version | Docker Engine v29+ |
| Notable service | Traefik ([traefik/traefik#12253](https://github.com/traefik/traefik/issues/12253)) |
| macOS | Docker Desktop builds that include Docker Engine v29 |
| Linux | Ubuntu 24.04 (other distros may require adapted steps) |

### Root Cause

Docker Engine v29 enforces a **newer minimum API version** by default. Older embedded clients (or services using older Docker SDKs) present API version `1.24`, which the new daemon rejects. The daemon exposes a configuration option to lower the minimum accepted API version; adjusting that setting restores compatibility.

### Solution — Option A: macOS (Docker Desktop)

1. Open **Docker Desktop → Settings → Docker Engine**.
2. Edit the JSON to include the `min-api-version` key. Merge this into the existing JSON:

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

> Keep the rest of your `daemon.json` as-is — only add or update the `"min-api-version"` field.

3. Click **Apply & Restart** in Docker Desktop.
4. Confirm affected services (Traefik, etc.) can now connect to the Docker daemon.

**Source:** [Docker Engine v29 blog post](https://www.docker.com/blog/docker-engine-version-29/)

### Solution — Option B: Ubuntu 24.04 (systemd)

_(Adapted from [traefik/traefik#12253](https://github.com/traefik/traefik/issues/12253#issuecomment-3515555316))_

1. Create a systemd override for the `docker.service` unit:

```bash
sudo systemctl edit docker.service
```

2. In the editor, add the following (in the `[Service]` section):

```ini
[Service]
Environment=DOCKER_MIN_API_VERSION=1.24
```

Save and close the editor.

3. Reload systemd and restart Docker:

```bash
sudo systemctl daemon-reload
sudo systemctl restart docker
```

4. Restart the affected services (e.g., Traefik) so they reconnect to the daemon.

> **Note:** Steps above were tested on Ubuntu 24.04. Other distros or Docker packaging methods may require adapted steps.

### Verification

- Traefik logs no longer show the `"client version ... is too old"` error.
- Services that previously failed with API-version errors connect and operate normally.

### Caveats

Lowering the server's minimum API version increases compatibility with older clients but may expose the daemon to older client behavior. Prefer **upgrading the client/service** to use a supported newer Docker API when feasible.

### Related

- [Traefik issue #12253](https://github.com/traefik/traefik/issues/12253)
- [Docker Engine v29 announcement](https://www.docker.com/blog/docker-engine-version-29/)
- [Ubuntu systemd override example](https://github.com/traefik/traefik/issues/12253#issuecomment-3515555316)

---

## See Also

- [Installation](Installation) — Setup guide (Docker, VM, Python)
- [Home](Home) — Project overview
