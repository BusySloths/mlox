"""Native developer terminal workstation bootstrap service."""

from __future__ import annotations

import logging
import shlex
from dataclasses import dataclass, field
from typing import Dict

from mlox.execution import TaskGroup
from mlox.service import AbstractService, ServiceCapability

logger = logging.getLogger(__name__)


@dataclass
class DeveloperTerminalService(AbstractService):
    """Install an opinionated terminal developer environment on a backend host."""

    capabilities = {ServiceCapability.DEVELOPER_TOOLS}
    install_claude_code: bool = True
    install_atuin: bool = True
    install_lazyvim: bool = True
    install_yazi: bool = True
    install_spaceship: bool = True
    install_pyenv: bool = True
    installed_tools: list[str] = field(default_factory=list, init=False)

    def _install_script(self) -> str:
        claude = "true" if self.install_claude_code else "false"
        atuin = "true" if self.install_atuin else "false"
        lazyvim = "true" if self.install_lazyvim else "false"
        yazi = "true" if self.install_yazi else "false"
        spaceship = "true" if self.install_spaceship else "false"
        pyenv = "true" if self.install_pyenv else "false"
        return f"""#!/usr/bin/env bash
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive
INSTALL_CLAUDE_CODE={claude}
INSTALL_ATUIN={atuin}
INSTALL_LAZYVIM={lazyvim}
INSTALL_YAZI={yazi}
INSTALL_SPACESHIP={spaceship}
INSTALL_PYENV={pyenv}
TARGET_USER="${{SUDO_USER:-$(id -un)}}"
TARGET_HOME="$(getent passwd "$TARGET_USER" | cut -d: -f6)"
if [ -z "$TARGET_HOME" ] || [ ! -d "$TARGET_HOME" ]; then
  TARGET_HOME="$HOME"
fi

apt-get update
apt-get install -yq \
  bash bat btop build-essential ca-certificates curl direnv fd-find fzf git \
  gnupg gzip htop jq libbz2-dev libffi-dev liblzma-dev libncursesw5-dev \
  libreadline-dev libsqlite3-dev libssl-dev libxml2-dev libxmlsec1-dev \
  llvm lsb-release make mc neovim nodejs npm pipx python3 python3-pip \
  ripgrep tar tk-dev tmux unzip wget xz-utils zlib1g-dev zsh

# Ubuntu/Debian package names the fd and bat binaries differently.
ln -sf /usr/bin/fdfind /usr/local/bin/fd 2>/dev/null || true
ln -sf /usr/bin/batcat /usr/local/bin/bat 2>/dev/null || true

npm install -g neovim tree-sitter-cli || true
if [ "$INSTALL_CLAUDE_CODE" = true ]; then
  npm install -g @anthropic-ai/claude-code || true
fi
if [ "$INSTALL_SPACESHIP" = true ]; then
  npm install -g spaceship-prompt || true
fi

if [ "$INSTALL_ATUIN" = true ] && ! command -v atuin >/dev/null 2>&1; then
  curl --proto '=https' --tlsv1.2 -LsSf https://setup.atuin.sh | sh || true
  if [ -x "$TARGET_HOME/.atuin/bin/atuin" ]; then
    ln -sf "$TARGET_HOME/.atuin/bin/atuin" /usr/local/bin/atuin
  fi
fi

if [ "$INSTALL_YAZI" = true ] && ! command -v yazi >/dev/null 2>&1; then
  tmpdir="$(mktemp -d)"
  arch="$(uname -m)"
  case "$arch" in
    x86_64|amd64) yazi_arch="x86_64-unknown-linux-gnu" ;;
    aarch64|arm64) yazi_arch="aarch64-unknown-linux-gnu" ;;
    *) yazi_arch="" ;;
  esac
  if [ -n "$yazi_arch" ]; then
    curl -fsSL "https://github.com/sxyazi/yazi/releases/latest/download/yazi-${{yazi_arch}}.zip" -o "$tmpdir/yazi.zip" || true
    if [ -s "$tmpdir/yazi.zip" ]; then
      unzip -q "$tmpdir/yazi.zip" -d "$tmpdir"
      find "$tmpdir" -type f -name yazi -exec install -m 0755 {{}} /usr/local/bin/yazi \\; -quit
      find "$tmpdir" -type f -name ya -exec install -m 0755 {{}} /usr/local/bin/ya \\; -quit
    fi
  fi
  rm -rf "$tmpdir"
fi


if [ "$INSTALL_PYENV" = true ] && ! command -v pyenv >/dev/null 2>&1; then
  if [ ! -d "$TARGET_HOME/.pyenv" ]; then
    sudo -u "$TARGET_USER" git clone https://github.com/pyenv/pyenv.git "$TARGET_HOME/.pyenv" || true
  fi
  if [ -x "$TARGET_HOME/.pyenv/bin/pyenv" ]; then
    ln -sf "$TARGET_HOME/.pyenv/bin/pyenv" /usr/local/bin/pyenv
  fi
fi

if [ "$INSTALL_LAZYVIM" = true ]; then
  install -d -o "$TARGET_USER" -g "$TARGET_USER" "$TARGET_HOME/.config"
  if [ ! -d "$TARGET_HOME/.config/nvim" ]; then
    sudo -u "$TARGET_USER" git clone https://github.com/LazyVim/starter "$TARGET_HOME/.config/nvim" || true
    rm -rf "$TARGET_HOME/.config/nvim/.git"
  fi

  install -d -o "$TARGET_USER" -g "$TARGET_USER" "$TARGET_HOME/.config/nvim/lua/plugins"
  NVIM_PLUGIN="$TARGET_HOME/.config/nvim/lua/plugins/mlox-dev-terminal.lua"
  cat > "$NVIM_PLUGIN" <<'MLOX_LAZYVIM_DEV_TERMINAL'
-- MLOX Developers Terminal Dream: Claude Code and Yazi integrations for LazyVim.
return {{
  {{
    "coder/claudecode.nvim",
    opts = {{}},
    keys = {{
      {{ "<leader>a", "", desc = "+ai", mode = {{ "n", "v" }} }},
      {{ "<leader>ac", "<cmd>ClaudeCode<cr>", desc = "Toggle Claude" }},
      {{ "<leader>af", "<cmd>ClaudeCodeFocus<cr>", desc = "Focus Claude" }},
      {{ "<leader>ar", "<cmd>ClaudeCode --resume<cr>", desc = "Resume Claude" }},
      {{ "<leader>aC", "<cmd>ClaudeCode --continue<cr>", desc = "Continue Claude" }},
      {{ "<leader>ab", "<cmd>ClaudeCodeAdd %<cr>", desc = "Add current buffer" }},
      {{ "<leader>as", "<cmd>ClaudeCodeSend<cr>", mode = "v", desc = "Send to Claude" }},
      {{ "<leader>aa", "<cmd>ClaudeCodeDiffAccept<cr>", desc = "Accept diff" }},
      {{ "<leader>ad", "<cmd>ClaudeCodeDiffDeny<cr>", desc = "Deny diff" }},
    }},
  }},
  {{
    "mikavilpas/yazi.nvim",
    version = "*",
    event = "VeryLazy",
    dependencies = {{
      {{ "nvim-lua/plenary.nvim", lazy = true }},
    }},
    keys = {{
      {{ "<leader>-", "<cmd>Yazi<cr>", mode = {{ "n", "v" }}, desc = "Open yazi at the current file" }},
      {{ "<leader>cw", "<cmd>Yazi cwd<cr>", desc = "Open yazi in nvim cwd" }},
      {{ "<c-up>", "<cmd>Yazi toggle<cr>", desc = "Resume yazi" }},
    }},
    opts = {{
      open_for_directories = true,
      open_multiple_tabs = true,
      keymaps = {{
        show_help = "<f1>",
      }},
    }},
    init = function()
      vim.g.loaded_netrwPlugin = 1
    end,
  }},
}}
MLOX_LAZYVIM_DEV_TERMINAL
  chown "$TARGET_USER:$TARGET_USER" "$NVIM_PLUGIN" || true
fi

ZSHRC="$TARGET_HOME/.zshrc"
touch "$ZSHRC"
chown "$TARGET_USER:$TARGET_USER" "$ZSHRC" || true
append_once() {{
  local line="$1"
  grep -qxF "$line" "$ZSHRC" 2>/dev/null || echo "$line" >> "$ZSHRC"
}}
append_once 'export EDITOR=nvim'
append_once 'export VISUAL=nvim'
append_once 'export PYENV_ROOT="$HOME/.pyenv"'
append_once '[[ -d $PYENV_ROOT/bin ]] && export PATH="$PYENV_ROOT/bin:$PATH"'
append_once 'command -v pyenv >/dev/null 2>&1 && eval "$(pyenv init - zsh)"'
append_once 'alias ll="ls -lah"'
append_once 'alias vim="nvim"'
append_once 'alias vi="nvim"'
append_once 'alias fm="yazi"'
append_once 'eval "$(direnv hook zsh)"'
append_once '[ -x "$HOME/.atuin/bin/atuin" ] && eval "$($HOME/.atuin/bin/atuin init zsh)"'
append_once 'command -v atuin >/dev/null 2>&1 && eval "$(atuin init zsh)"'
append_once '[ -f "$(npm root -g 2>/dev/null)/spaceship-prompt/spaceship.zsh" ] && source "$(npm root -g)/spaceship-prompt/spaceship.zsh"'
chown "$TARGET_USER:$TARGET_USER" "$ZSHRC" || true

if command -v zsh >/dev/null 2>&1; then
  chsh -s "$(command -v zsh)" "$TARGET_USER" || true
fi
"""

    def setup(self, conn) -> None:
        self.exec.fs_create_dir(conn, self.target_path)
        script_path = f"{self.target_path}/install-developer-terminal.sh"
        self.exec.fs_write_file(conn, script_path, self._install_script())
        quoted_script_path = shlex.quote(script_path)
        self.exec.execute(
            conn, f"chmod +x {quoted_script_path}", group=TaskGroup.FILESYSTEM
        )
        self.exec.execute(
            conn, quoted_script_path, group=TaskGroup.SYSTEM_PACKAGES, sudo=True
        )
        self.state = "running"

    def teardown(self, conn) -> None:
        self.exec.fs_delete_dir(conn, self.target_path)
        self.state = "un-initialized"

    def spin_up(self, conn) -> bool:
        self.state = "running"
        return True

    def spin_down(self, conn) -> bool:
        self.state = "stopped"
        return True

    def check(self, conn) -> Dict[str, str]:
        command = "command -v zsh git nvim mc yazi atuin claude pyenv >/dev/null"
        try:
            self.exec.execute(conn, command, group=TaskGroup.AD_HOC)
            self.state = "running"
            return {"status": "running"}
        except Exception as exc:
            logger.warning("Developer terminal check failed: %s", exc)
            self.state = "unknown"
            return {"status": "unknown"}

    def get_secrets(self) -> Dict[str, Dict]:
        return {}
