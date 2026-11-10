# Developers Terminal Dream

Connect to the backend over SSH and run `herdr`. Open a pane in the desired
project and start `claude`, `codex`, `opencode`, or `omp`. Authenticate each
agent with its provider separately; installation does not supply credentials.
Herdr keeps processes running after a client disconnect; after a machine restart,
processes must be restarted, although supported sessions can be restored. Press
Ctrl-b q to detach and run `herdr` to reconnect.

The installer provides the `xterm-ghostty` terminfo entry when the host lacks
it, so Ghostty can be used over SSH on older Ubuntu releases. Existing
installations can be fixed without reinstalling the service by running this on
the local Ghostty machine (substitute the SSH host):

```sh
infocmp -x xterm-ghostty | ssh user@host 'tic -x -o "$HOME/.terminfo" -'
```

This installs the entry for that SSH user. For a temporary fallback, connect
with `ssh -o SetEnv=TERM=xterm-256color user@host`; some Ghostty-specific
terminal features will then be unavailable.

For richer agent status and session restoration, run the following as the SSH
user after initializing the agents' configuration directories:

```sh
herdr integration install claude
herdr integration install codex
herdr integration install opencode
herdr integration install omp
```

These commands modify the agents' user configuration. See the [Herdr integration
documentation](https://herdr.dev/tui/docs/integrations/) for requirements and
what each integration supports. OMP reports state but does not offer the same
native session restoration as the other integrations.

[terminal-browser](https://github.com/zenbu-labs/terminal-browser#ssh) can be
used over SSH. Its recommended approach is to install it on a local machine with
a supported graphical terminal and run `terminal-browser open --ssh user@host
localhost:PORT`. The browser runs locally and proxies network requests through
the backend. Running it on the VPS over SSH is also possible with a compatible
terminal and the browser's runtime dependencies, but sends rendered frames over
the connection. Pane integration depends on the terminal and multiplexer. The
service does not install terminal-browser or configure access between a remote
agent and a locally running browser.

The existing teardown removes Claude and Codex user state, including credentials
and sessions; back up anything needed before removing the service. Agent
credentials and workspaces should also be backed up separately from the host.
