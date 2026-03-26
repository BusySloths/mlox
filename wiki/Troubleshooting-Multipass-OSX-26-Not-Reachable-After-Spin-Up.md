# VM / Multipass / macOS 26: Not Reachable After Spin Up

> **Date:** 2025-11-23  
> **Author:** @nicococo  
> **Status:** Fixed

---

## Update

- If you use applications installed with MLOX on VMs, also allow the corresponding client apps to connect, for example your browser and Multipass.
- Check your local firewall settings as well.

---

## Summary

Multipass can start a VM successfully on macOS 26, but the instance may still be unreachable from the host because macOS privacy settings block local network access for the app used to launch or communicate with the VM.

---

## Symptoms

- `multipass list` shows the instance as running, but `multipass shell`, SSH, or ping from the host fails or hangs.
- VS Code Remote / Remote - SSH cannot connect to the instance.
- `ping <vm-ip>` times out or reports `no route to host`.
- Multipass logs do not show an obvious networking failure on the Multipass side.

---

## Environment

| Item | Value |
|------|-------|
| Host OS | macOS 26 |
| VM manager | Multipass |
| Client apps | Terminal.app, iTerm, VS Code |
| Multipass version | Fill in if known |
| Network | Default Multipass networking |

---

## Steps to Reproduce

```bash
multipass launch --name test-vm
multipass list
multipass shell test-vm
```

You can reproduce the same issue when trying to connect from VS Code Remote after the VM is up.

---

## Root Cause

On macOS 26, privacy settings can block an app from finding and communicating with local devices. If Terminal, iTerm, or VS Code does not have Local Network access, it cannot reach a Multipass-hosted VM on the host's local network interface.

---

## Solution / Workaround

1. Open **System Settings** on macOS.
2. Go to **Privacy & Security** -> **Local Network**.
3. Enable the app you use to access the VM:
   - `Terminal.app`
   - `iTerm`
   - `Visual Studio Code`
4. Quit and reopen the affected app.
5. If needed, restart the instance:

```bash
multipass stop <instance-name>
multipass start <instance-name>
```

6. Retry the connection:

```bash
multipass shell <instance-name>
```

---

## Verification

- `multipass shell <instance-name>` opens a shell in the VM.
- `ping <vm-ip>` from the host returns replies.
- VS Code Remote connects and opens a workspace in the VM.

---

## Notes

- If you use multiple terminals or editors, grant permission to each one as needed.
- macOS may only fully apply the change after the app is restarted.
- If the issue persists, restart the Multipass service or the host as a last resort.
- Document which client app is in use so teammates know what to enable.

---

## Related

- Add an internal issue, CI run, or discussion link here if one exists.

---

## See Also

- [Troubleshooting](Troubleshooting) — Troubleshooting index
- [Installation](Installation) — Multipass-based integration test setup
