---
slug: first-steps
title: "Your first project, five minutes from now"
type: tutorial
status: published
mlox_version: 0.6.1
# One capture name per shot; each becomes website/src/captures/first-steps/<name>.html.
shots:
  - install
  - login
  - templates
  - vm_dialog
  - server_ready
  - catalog
  - memos_ready
  - cleanup
# Outputs are listed in content/registry.yaml.
---

# Your first project, five minutes from now

The pilot tutorial: install MLOX, create a project, let MLOX launch a local
Ubuntu VM with Docker, and run one catalog app (Memos) on it, all from the
terminal UI. It is published as `website/src/pages/learn/first-steps.astro`.

Like `tui-teaser`, this is recorded as terminal captures, not a screen
recording: `content/scripts/capture.py` snapshots the pane while the steps run,
and the frame times give the measured timings. Each chapter below lists what to
do, what to show, and the capture it produces. Keep this script and the page in
step: when a chapter changes here, re-run it and update the page.

## Recording setup

- A fresh folder with no `*.mlox` files, a clean `PATH` with `uv tool`'s
  `~/.local/bin` first, and no existing VM with the server name below.
- A plain prompt so no hostname or user leaks: `exec zsh -f`, `PS1='$ '`,
  `RPROMPT=`.
- One person drives, one keeps the time from `mlox tui` onwards. Typing and
  reading time count; nothing is cut.
- Names used on screen: project `my-awesome-project`, server
  `my-awesome-server`.

## Chapter: before

Prerequisites, not recorded: uv, Multipass, room for one VM (2 CPUs, 4 GB RAM,
20 GB disk). On macOS, allow Multipass and the terminal under Privacy & Security
› Developer Tools.

## Chapter: install

`uv tool install 'busysloths-mlox[tui]'`

Show: uv resolving the packages and installing one executable, `mlox`.
Capture: `install`. If `mlox tui` says *No such command*, an older `mlox` is
earlier on the path (page note).

## Chapter: project

`mlox tui`, type a project name and password, press **Create**.

Show: the login screen with the name filled in and the Create button.
Capture: `login` (marks on the name field and Create). Point out that the
password encrypts everything and cannot be reset.

## Chapter: server

**Add Bundle** › template **Ubuntu Multipass VM (Docker)** › **Configure & Add
Server** › name the VM › **Add Server**.

Show: the template list with the macOS note in the overview, then the form.
Captures: `templates` (template, note, Configure button), `vm_dialog` (name
field, Add Server). The server appears as pending.

## Chapter: setup

Select the server, **Setup Bundle**, wait.

Show: the server running with its Docker backend and address in the tree, and
the new Add Service action. Capture: `server_ready`; pick a frame that already
shows the state `running`. Mention that setup locks SSH down: no password,
keyboard-interactive or root logins, MLOX's own key only.

## Chapter: app

**Add Service** › **Application: Memos** › **Configure & Add Service** ›
**Setup Service**.

Show: the catalog with the Memos overview (capabilities, port 5230).
Capture: `catalog`. Ports from the template are intended, not final.

## Chapter: open

**Check Health**, then **Open Web UI**; accept the self-signed certificate,
create the Memos admin, write a note.

Show: Memos under the server, the two buttons, and the notifications.
Capture: `memos_ready`.

## Chapter: cleanup

Quit with `q`, then `multipass list`, `multipass delete my-awesome-server
--purge`, `multipass list`.

Capture: `cleanup` (the VM listed, then gone). Delete the `.mlox` file for a
completely fresh start.

## Chapter: time

The measured steps from the recorded run (seconds), taken from the capture
frame times and kept in the page's `timings` array:

| Step | Seconds |
| --- | --- |
| Install MLOX | 13 |
| Create a project | 18 |
| Add a Multipass server | 48 |
| Server setup (VM + Docker) | 104 |
| Add Memos from the catalog | 33 |
| Memos setup | 11 |
| Health check, open in browser | 26 |
| **Total** | **253 (4 min 13 s)** |

## Producing the outputs

`captures.json` names one frame per shot with its rows and crop; `redact.json`
maps the VM address, the generated MLOX user and the local user name to
same-length stand-ins.

```sh
W=content/.work/first-steps
uv run python -m content.scripts.captures $W/captures.json --frames $W/frames \
  --map $W/redact.json --out website/src/captures/first-steps
```

The page includes them with `<TermCapture set="first-steps" name="…">`.
