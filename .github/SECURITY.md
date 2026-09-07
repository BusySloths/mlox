# Security Policy

## Reporting a Vulnerability

**Please do not report suspected vulnerabilities in public GitHub issues.**

Preferred channel: **GitHub private vulnerability reporting** — open the
repository, go to *Security → Report a vulnerability*, and submit a private
report. This keeps the details confidential and lets us coordinate a fix and a
disclosure timeline with you directly.

If you cannot use private vulnerability reporting, email
[contact@mlox.org](mailto:contact@mlox.org) with `[security]` in the subject.
Please avoid sending secrets or exploit payloads by email.

Please include, where applicable:

- the affected version (or commit) and the component involved
  (CLI, TUI, project file handling, secret manager integration, remote
  execution, packaging)
- a minimal description or reproduction of the issue
- the impact you believe it has, and any preconditions

We aim to acknowledge reports within **5 business days** and will keep you
informed about diagnosis, fix, and planned disclosure. Once a fix is released,
we will credit you in the release notes unless you prefer to remain anonymous.

## Supported Versions

Security fixes are applied to the latest released version and `main`.
MLOX is pre-1.0 and moves quickly — please upgrade before reporting.

| Version | Supported |
| --- | --- |
| latest release | ✅ |
| older releases | ❌ (upgrade first) |
| `main` | ✅ |

## Scope

In scope:

- the MLOX codebase (CLI, TUI, project/workspace handling, executors,
  packaging)
- the handling of encrypted project files, secret manager keyfiles, and
  credentials (`MLOX_PROJECT_PASSWORD`, keyfiles, tokens) — including anything
  that leaks them into logs, command output, or exported state

Out of scope:

- vulnerabilities in third-party services *deployed by* MLOX (Docker images,
  Kubernetes services, etc.) — please report those to the respective upstream
  projects; misconfigurations that MLOX hands through to a service are a
  boundary we want to understand, so when in doubt, report anyway
- social engineering, or attacks that require physical access to an
  already-trusted machine

## Trust Boundaries

The full threat model is being developed (see the *Security & trust* roadmap
item in `docs/DOCTRINE.md`). The boundaries that matter today:

1. **Project files** — single encrypted SQLCipher file per project; the
   project password is the root secret.
2. **Secret manager keyfiles** — the keyfile unlocks stored credentials for
   deployed services; whoever holds it can read every secret in the project.
3. **Remote execution** — MLOX runs commands on user servers via SSH and
   container runtimes; those credentials and commands must never be logged or
   rendered in cleartext.

If you find data flowing across one of these boundaries that should not
(e.g. a password appearing in a log, CLI output, or the TUI), that is a
security issue by definition — please report it.
