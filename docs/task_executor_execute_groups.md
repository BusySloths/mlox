# Task Executor Command Grouping

## Overview
The current codebase issues remote shell commands through `UbuntuTaskExecutor.exec_command` (and the local stand-in on development machines). These direct invocations are spread across servers, services, and supporting utilities, each encoding their own command strings, `sudo` usage, and expected outputs. To refactor the executor into a portable task interface, the calls should be bucketed into cohesive groups that can share task specifications, parameters, and post-processing rules. The sections below summarise each group, representative commands, and design notes that will help translate the existing behaviour into reusable tasks.

### Execution Semantics to Preserve
* `exec_command` accepts the raw command string plus `sudo` and `pty` flags, records history, and returns stripped stdout (or `None` on allowed `sudo` failures).【F:mlox/executors.py†L75-L114】
* The local backend mirrors this contract by routing `run`/`sudo` to a subprocess helper that raises on non-zero exits to stay aligned with Fabric semantics.【F:mlox/servers/local/local.py†L44-L110】
* Any task abstraction must therefore: (1) expose privilege escalation and pseudo-terminal options, (2) propagate stdout/stderr/exit-code metadata, and (3) surface recoverable failures in the same places as the current helper.

## Command Groups

### 1. System Package Management & Updates
* **Purpose:** Prepare hosts by updating package indices, resolving dpkg locks, and installing or purging packages.
* **Representative commands:** `dpkg --configure -a`, `apt-get update`, `apt-get upgrade`, `apt-get install`, `apt-get purge` with noninteractive flags and lock timeouts.【F:mlox/servers/ubuntu/native.py†L81-L126】【F:mlox/servers/ubuntu/docker.py†L24-L75】
* **Contexts:** Ubuntu native server bootstrap, Docker backend installation/removal.
* **Task shape:** Accept package lists (possibly grouped), noninteractive toggles, and optional retry/lock-wait policies. Return success/failure plus any stdout snippets that feed subsequent steps.

### 2. Service Control & Systemd Management
* **Purpose:** Start, stop, enable, disable, or inspect long-running services via `systemctl`.
* **Representative commands:** `systemctl start/stop/restart`, `systemctl is-active`, `systemctl is-enabled`, `systemctl status` for services such as Docker, k3s, and sshd.【F:mlox/servers/ubuntu/docker.py†L63-L151】【F:mlox/servers/ubuntu/k3s.py†L50-L182】【F:mlox/servers/ubuntu/native.py†L330-L352】
* **Task shape:** Parameterise on service name, desired action, and whether a pseudo-TTY is required. Capture boolean state results for status queries.

### 3. Container Runtime Operations
* **Purpose:** Manage Docker Engine, docker-compose deployments, and runtime diagnostics.
* **Representative commands:** `docker compose up/down`, `docker ps`, `docker inspect`, `docker logs`, `docker version` executed with sudo and structured output parsing.【F:mlox/executors.py†L260-L377】【F:mlox/servers/ubuntu/docker.py†L86-L151】【F:mlox/services/postgres/docker.py†L46-L76】
* **Contexts:** Service lifecycle helpers (Postgres, Redis, etc.), backend health checks, generic executor utilities.
* **Task shape:** Tasks should encapsulate compose stack operations, container listing/state retrieval, and log tailing, normalising JSON or tabular responses as structured data.

### 4. Kubernetes & Helm Orchestration
* **Purpose:** Interact with clusters to install charts, patch services, and query status.
* **Representative commands:** `kubectl get/patch/apply`, `kubectl create token`, `helm repo add`, `helm upgrade --install`, `helm status` with kubeconfig arguments.【F:mlox/servers/ubuntu/k3s.py†L50-L174】【F:mlox/services/kubeapps/k8s.py†L22-L145】【F:mlox/services/k8s_dashboard/k8s.py†L18-L97】
* **Task shape:** Accept chart/namespace identifiers, kubeconfig paths, and patch payloads. Return parsed status (e.g., deployment state, service URLs) instead of raw strings where possible.

### 5. Filesystem & Configuration Management
* **Purpose:** Create, remove, copy, or modify files and directories, including sed-based replacements and appending lines.
* **Representative commands:** `mkdir -p`, `rm -rf`, `cp -r`, `ln -s`, `touch`, `echo >>`, `sed -i`, `mv` for privileged writes, and custom listings via `find`/`ls`.
* **Call sites:** General executor helpers invoked by services for templating, TLS prep, and configuration management.【F:mlox/executors.py†L425-L637】
* **Task shape:** Provide tasks for directory management, file copy/upload with sudo escalation, in-place text substitution, and metadata listings. Each task should track whether sudo was required and propagate resulting paths or directory states.

### 6. User & Access Provisioning
* **Purpose:** Create local users, manage sudo membership, and set up SSH credentials.
* **Representative commands:** `useradd`, `usermod`, `id -u`, `ls -l /home`, shell pipelines to create `.ssh` directories, generate keys, and adjust permissions.【F:mlox/executors.py†L147-L196】【F:mlox/servers/ubuntu/native.py†L176-L246】
* **Task shape:** Accept usernames, passwords, and role flags, returning created identifiers (UIDs, home paths). SSH bootstrap tasks should orchestrate directory creation, key generation, and authorized_keys updates while reporting generated material.

### 7. Security Assets & TLS Material
* **Purpose:** Generate certificates and keys for HTTPS endpoints.
* **Representative commands:** `openssl genrsa`, `openssl req`, `openssl x509`, followed by permission hardening via `chmod` in prepared directories.【F:mlox/executors.py†L208-L260】
* **Task shape:** Parameterise on subject names, config templates, and target paths. Emit resulting certificate/key locations and optionally the certificate contents for storage.

### 8. Version Control & Deploy Keys
* **Purpose:** Clone or update Git repositories (public and private) and produce deploy keys.
* **Representative commands:** `git clone`, `git pull`, `ssh-keygen`, and git commands wrapped with `GIT_SSH_COMMAND` for deploy keys.【F:mlox/executors.py†L388-L406】【F:mlox/services/github/service.py†L112-L204】
* **Task shape:** Tasks should manage repository paths, authentication material, and status flags (`cloned`, `modified_timestamp`). Key generation tasks must surface both public and private keys securely.

### 9. Networking, Downloads, & Diagnostics
* **Purpose:** Fetch remote resources, gather host metadata, and perform health checks.
* **Representative commands:** `curl` to download installers or GPG keys, `host`, `uname`, `df`, `lscpu`-style pipelines, and ad-hoc `kubectl`/`helm` queries for verification.【F:mlox/servers/ubuntu/docker.py†L33-L60】【F:mlox/servers/ubuntu/k3s.py†L50-L74】【F:mlox/servers/ubuntu/native.py†L135-L170】
* **Task shape:** Bundle network fetches (with destination paths and checksum hooks) and diagnostics (return structured metrics like CPU/RAM/disk, DNS resolution). Distinguish between mandatory and best-effort probes to mirror current warning behaviour.

### 10. Ad-hoc Command Execution Interfaces
* **Purpose:** Provide a passthrough for user-issued shell commands in interactive tools (e.g., Streamlit terminal panel) and scripted utilities.
* **Representative commands:** Arbitrary strings captured from UI inputs and executed via the executor with explicit `pty` settings.【F:mlox/view/terminal.py†L40-L73】
* **Task shape:** Define a generic "run shell command" task that takes a user-supplied command plus execution options, returning stdout/stderr so higher layers can render interactive feedback while respecting existing safety checks.

## Call-site Totals
An AST scan of the current codebase finds **127 direct calls** to `exec_command` (excluding tests and the executor implementation itself). Distributing those invocations across the groups above gives the following migration workload:

| Group | Description | Call sites |
| --- | --- | --- |
| 1 | System Package Management & Updates | 13 |
| 2 | Service Control & Systemd Management | 9 |
| 3 | Container Runtime Operations | 23 |
| 4 | Kubernetes & Helm Orchestration | 30 |
| 5 | Filesystem & Configuration Management | 22 |
| 6 | User & Access Provisioning | 9 |
| 7 | Security Assets & TLS Material | 9 |
| 8 | Version Control & Deploy Keys | 6 |
| 9 | Networking, Downloads, & Diagnostics | 5 |
| 10 | Ad-hoc Command Execution Interfaces | 1 |

These totals indicate the minimum number of task-wrapper function calls needed once every existing `exec_command` usage is replaced with its corresponding task abstraction.

## Using the Groups
When migrating to task-based execution:
1. Map each existing call site to the appropriate group, then replace the inline command with a task invocation carrying the same parameters (`sudo`, `pty`, expected outputs).
2. Implement reusable task classes or descriptors per group so services and servers can declare intent without embedding raw shell.
3. Ensure task responses expose structured data wherever callers currently parse stdout (e.g., Docker JSON, `kubectl` table parsing) to remove duplicate parsing logic.

These groupings strike a balance between coverage (every current `exec_command` usage fits one of the categories) and maintainability (each group targets a coherent subsystem with shared inputs and outputs), enabling a smooth transition toward a platform-agnostic task executor.
