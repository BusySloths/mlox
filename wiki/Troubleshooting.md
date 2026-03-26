# Troubleshooting

Known issues, environment-specific pitfalls, and practical fixes for MLOX-related workflows.

---

## Contents

1. [VM / Multipass / macOS 26: Not Reachable After Spin Up](#vm--multipass--macos-26-not-reachable-after-spin-up)
2. [Docker 29: "client version ... is too old"](#docker-29-client-version--is-too-old)

---

## VM / Multipass / macOS 26: Not Reachable After Spin Up

Multipass VMs may start successfully on macOS 26 but still be unreachable from Terminal, iTerm, or VS Code because macOS blocks local network access for the app used to connect.

→ Read the full guide: [VM / Multipass / macOS 26: Not Reachable After Spin Up](Troubleshooting-Multipass-OSX-26-Not-Reachable-After-Spin-Up)

---

## Docker 29: "client version ... is too old"

After upgrading to Docker Engine 29, older embedded Docker clients such as the one used by some Traefik builds can fail to connect unless the daemon's minimum accepted API version is lowered.

→ Read the full guide: [Docker 29: "client version ... is too old"](Troubleshooting-Docker-29-Client-Version-Too-Old)

---

## See Also

- [Home](Home) — Project overview
- [Installation](Installation) — Setup and test environment basics
- [Contributing](Contributing) — How to improve the docs or report new issues
