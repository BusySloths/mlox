# Execution Layer

This package provides reusable primitives for work on local and remote systems.

## Structure

- `base.py`: task contracts, groups, and execution history.
- `system.py`, `filesystem.py`, `security.py`: host operations.
- `docker.py`, `kubernetes.py`: container and cluster operations.
- `git.py`, `firewall.py`: version-control and network helpers.

## Workflow

Servers provide connections and executors. Service and server implementations
call executor methods, which run commands and record structured history.

## System Role

This layer isolates command construction and remote side effects. UI code and
application use cases should not issue ad-hoc shell commands.

