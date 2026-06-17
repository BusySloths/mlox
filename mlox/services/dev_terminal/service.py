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
MIN_NVIM_VERSION=0.11.2
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
  llvm locales lsb-release make mc nodejs npm pipx python3 python3-pip \
  ripgrep snapd tar tk-dev tmux unzip wget xz-utils zlib1g-dev zsh

locale-gen C.UTF-8 >/dev/null 2>&1 || true
update-locale LANG=C.UTF-8 LC_CTYPE=C.UTF-8 >/dev/null 2>&1 || true

# Ubuntu/Debian package names the fd and bat binaries differently.
ln -sf /usr/bin/fdfind /usr/local/bin/fd 2>/dev/null || true
ln -sf /usr/bin/batcat /usr/local/bin/bat 2>/dev/null || true

nvim_version() {{
  if command -v nvim >/dev/null 2>&1; then
    nvim --version | sed -n '1s/^NVIM v//p' | cut -d- -f1
  fi
}}

nvim_version_meets_min() {{
  local version
  version="$(nvim_version)"
  [ -n "$version" ] && dpkg --compare-versions "$version" ge "$MIN_NVIM_VERSION"
}}

if ! nvim_version_meets_min; then
  systemctl enable --now snapd.socket >/dev/null 2>&1 || true
  snap wait system seed.loaded >/dev/null 2>&1 || true
  snap install nvim --classic
  if [ -x /snap/bin/nvim ]; then
    ln -sf /snap/bin/nvim /usr/local/bin/nvim
  fi
fi

if ! nvim_version_meets_min; then
  echo "Neovim $MIN_NVIM_VERSION or newer is required for LazyVim." >&2
  exit 1
fi

npm install -g neovim tree-sitter-cli || true
if [ "$INSTALL_CLAUDE_CODE" = true ]; then
  npm install -g @anthropic-ai/claude-code || true
fi
if [ "$INSTALL_SPACESHIP" = true ]; then
  npm install -g spaceship-prompt || true
fi

if [ "$INSTALL_ATUIN" = true ] && ! command -v atuin >/dev/null 2>&1 && [ ! -x "$TARGET_HOME/.atuin/bin/atuin" ]; then
  sudo -H -u "$TARGET_USER" env HOME="$TARGET_HOME" sh -c \
    "curl --proto '=https' --tlsv1.2 -LsSf https://setup.atuin.sh | sh" || true
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


if [ "$INSTALL_PYENV" = true ]; then
  install -d -o "$TARGET_USER" -g "$TARGET_USER" "$TARGET_HOME/.pyenv"
  if [ ! -x "$TARGET_HOME/.pyenv/bin/pyenv" ]; then
    if [ -d "$TARGET_HOME/.pyenv/.git" ]; then
      sudo -H -u "$TARGET_USER" env HOME="$TARGET_HOME" git -C "$TARGET_HOME/.pyenv" pull --ff-only || true
    elif [ -z "$(find "$TARGET_HOME/.pyenv" -mindepth 1 -maxdepth 1 -print -quit)" ]; then
      sudo -H -u "$TARGET_USER" env HOME="$TARGET_HOME" git clone https://github.com/pyenv/pyenv.git "$TARGET_HOME/.pyenv" || true
    else
      sudo -H -u "$TARGET_USER" env HOME="$TARGET_HOME" git -C "$TARGET_HOME/.pyenv" init || true
      sudo -H -u "$TARGET_USER" env HOME="$TARGET_HOME" git -C "$TARGET_HOME/.pyenv" remote add origin https://github.com/pyenv/pyenv.git 2>/dev/null || \
        sudo -H -u "$TARGET_USER" env HOME="$TARGET_HOME" git -C "$TARGET_HOME/.pyenv" remote set-url origin https://github.com/pyenv/pyenv.git || true
      sudo -H -u "$TARGET_USER" env HOME="$TARGET_HOME" git -C "$TARGET_HOME/.pyenv" fetch --depth 1 origin master || true
      sudo -H -u "$TARGET_USER" env HOME="$TARGET_HOME" git -C "$TARGET_HOME/.pyenv" checkout -f FETCH_HEAD || true
    fi
  fi
  chown -R "$TARGET_USER:$TARGET_USER" "$TARGET_HOME/.pyenv" || true
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
remove_line() {{
  local line="$1"
  if [ -f "$ZSHRC" ]; then
    grep -vxF "$line" "$ZSHRC" > "$ZSHRC.tmp" 2>/dev/null || true
    cat "$ZSHRC.tmp" > "$ZSHRC"
    rm -f "$ZSHRC.tmp"
  fi
}}
remove_line '[ -x "$HOME/.atuin/bin/atuin" ] && eval "$($HOME/.atuin/bin/atuin init zsh)"'
remove_line 'command -v atuin >/dev/null 2>&1 && eval "$(atuin init zsh)"'
remove_line '[[ -d $PYENV_ROOT/bin ]] && export PATH="$PYENV_ROOT/bin:$PATH"'
remove_line 'command -v pyenv >/dev/null 2>&1 && eval "$(pyenv init - zsh)"'
append_once 'export EDITOR=nvim'
append_once 'export VISUAL=nvim'
append_once 'export LANG=C.UTF-8'
append_once 'export LC_CTYPE=C.UTF-8'
append_once 'unset LC_ALL'
append_once 'export PYENV_ROOT="$HOME/.pyenv"'
append_once '[[ -d "$PYENV_ROOT/bin" ]] && export PATH="$PYENV_ROOT/bin:$PATH"'
append_once '[[ -d "$PYENV_ROOT/shims" ]] && export PATH="$PYENV_ROOT/shims:$PATH"'
append_once '[[ -d "$HOME/.atuin/bin" ]] && export PATH="$HOME/.atuin/bin:$PATH"'
append_once 'command -v pyenv >/dev/null 2>&1 && eval "$(pyenv init -)"'
append_once 'alias ll="ls -lah"'
append_once 'alias vim="nvim"'
append_once 'alias vi="nvim"'
append_once 'alias fm="yazi"'
append_once 'eval "$(direnv hook zsh)"'
append_once 'if [ -x "$HOME/.atuin/bin/atuin" ]; then eval "$($HOME/.atuin/bin/atuin init zsh)"; elif command -v atuin >/dev/null 2>&1; then eval "$(atuin init zsh)"; fi'
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
        command = """command -v zsh git nvim mc yazi atuin claude pyenv >/dev/null
nvim_version="$(nvim --version | sed -n '1s/^NVIM v//p' | cut -d- -f1)"
[ -n "$nvim_version" ] && dpkg --compare-versions "$nvim_version" ge 0.11.2"""
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
